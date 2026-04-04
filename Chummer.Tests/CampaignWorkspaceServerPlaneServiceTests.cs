using Chummer.Campaign.Contracts;
using System.Reflection;
using Chummer.Control.Contracts.Support;
using Chummer.Run.Api.Contracts;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.ViewModels;
using Chummer.Run.Contracts.Community;
using Xunit;

namespace Chummer.Tests;

public sealed class CampaignWorkspaceServerPlaneServiceTests
{
    [Fact]
    public void PrepLibraryQueryTokensSplitAndNormalizePunctuation()
    {
        IReadOnlyList<string> tokens = InvokeBuildTokens("  Opposition, season-control / audit  ");

        Assert.Contains("opposition", tokens);
        Assert.Contains("season", tokens);
        Assert.Contains("eventcontrol", tokens);
        Assert.Contains("operation", tokens);
        Assert.Contains("audit", tokens);
    }

    [Fact]
    public void PrepLibraryQueryMatchingRequiresAllTokensAcrossSearchSurfaces()
    {
        var packet = new GovernedPrepPacketSummary(
            PacketId: "opposition:demo",
            Kind: "opposition_packet",
            Title: "Neon Cradle opposition packet",
            Summary: "Active pressure stays tied to the current season lane.",
            BindingSummary: "Bound to the return lane and audit receipts.",
            Reusable: true,
            SearchTerms: ["opposition", "season", "roster"],
            EvidenceLines: ["GM audit line: roster movement receipt captured."],
            UpdatedAtUtc: DateTimeOffset.Parse("2026-04-03T00:00:00Z"));

        IReadOnlyList<string> positiveTokens = InvokeBuildTokens("opposition audit");
        IReadOnlyList<string> negativeTokens = InvokeBuildTokens("opposition matrix");

        Assert.True(InvokeMatches(packet, positiveTokens));
        Assert.False(InvokeMatches(packet, negativeTokens));
    }

    [Fact]
    public void PrepLibraryQueryMatchingSupportsOpForShorthandAcrossWhitespaceAndPunctuation()
    {
        var packet = new GovernedPrepPacketSummary(
            PacketId: "opposition:opfor",
            Kind: "opposition_packet",
            Title: "Neon Cradle opfor packet",
            Summary: "Opposition pressure stays tied to the governed event lane.",
            BindingSummary: "Bound to campaign return and opposition control receipts.",
            Reusable: true,
            SearchTerms: ["opfor", "opposition", "threat"],
            EvidenceLines: ["Opfor opposition board remains active for the next launch window."],
            UpdatedAtUtc: DateTimeOffset.Parse("2026-04-04T00:00:00Z"));

        Assert.True(InvokeMatches(packet, InvokeBuildTokens("opfor")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("opforce")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("op-for")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("op force")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("op_force")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("opforces")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("opfors")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("op-forces")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("op forces")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("op_fors")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("oppositions")));
        Assert.False(InvokeMatches(packet, InvokeBuildTokens("matrixforce")));
    }

    [Fact]
    public void PrepLibraryQueryMatchingSupportsCompactShorthandAcrossWhitespaceBoundaries()
    {
        var packet = new GovernedPrepPacketSummary(
            PacketId: "prep:demo",
            Kind: "prep_launch_packet",
            Title: "Neon Cradle prep library packet",
            Summary: "Prep library remains governed for launch.",
            BindingSummary: "Bound to campaign return and audit lanes.",
            Reusable: true,
            SearchTerms: ["prep", "library", "packet"],
            EvidenceLines: ["GM prep library receipt captured."],
            UpdatedAtUtc: DateTimeOffset.Parse("2026-04-03T00:00:00Z"));

        IReadOnlyList<string> compactTokens = InvokeBuildTokens("preplibrary");
        IReadOnlyList<string> pluralPacketTokens = InvokeBuildTokens("packets");
        IReadOnlyList<string> splitPluralPacketTokens = InvokeBuildTokens("prep packets");
        IReadOnlyList<string> negativeTokens = InvokeBuildTokens("matrixlibrary");

        Assert.True(InvokeMatches(packet, compactTokens));
        Assert.True(InvokeMatches(packet, pluralPacketTokens));
        Assert.True(InvokeMatches(packet, splitPluralPacketTokens));
        Assert.False(InvokeMatches(packet, negativeTokens));
    }

    [Fact]
    public void PrepLibraryQueryMatchingSupportsEventCtrlShorthandAcrossWhitespaceBoundaries()
    {
        var packet = new GovernedPrepPacketSummary(
            PacketId: "event:demo",
            Kind: "event_control_packet",
            Title: "Dockyard event control board",
            Summary: "Season operations remain governed for launch.",
            BindingSummary: "Bound to campaign return and opposition lanes.",
            Reusable: true,
            SearchTerms: ["event", "control", "seasonops"],
            EvidenceLines: ["Event control receipt captured for next checkpoint."],
            UpdatedAtUtc: DateTimeOffset.Parse("2026-04-03T00:00:00Z"));

        IReadOnlyList<string> compactTokens = InvokeBuildTokens("eventctrl");
        IReadOnlyList<string> compactCtlTokens = InvokeBuildTokens("eventctl");
        IReadOnlyList<string> compactCtlPluralTokens = InvokeBuildTokens("eventctls");
        IReadOnlyList<string> compactPluralAbbrevTokens = InvokeBuildTokens("eventctrls");
        IReadOnlyList<string> compactPluralTokens = InvokeBuildTokens("eventcontrols");
        IReadOnlyList<string> negativeTokens = InvokeBuildTokens("matrixctrl");

        Assert.True(InvokeMatches(packet, compactTokens));
        Assert.True(InvokeMatches(packet, compactCtlTokens));
        Assert.True(InvokeMatches(packet, compactCtlPluralTokens));
        Assert.True(InvokeMatches(packet, compactPluralAbbrevTokens));
        Assert.True(InvokeMatches(packet, compactPluralTokens));
        Assert.False(InvokeMatches(packet, negativeTokens));
    }

    [Fact]
    public void PrepLibraryQueryMatchingSupportsSeasonOpsShorthandAcrossWhitespaceBoundaries()
    {
        var packet = new GovernedPrepPacketSummary(
            PacketId: "event:season",
            Kind: "event_control_packet",
            Title: "Dockyard season operations board",
            Summary: "Season operations stay governed for the next launch window.",
            BindingSummary: "Bound to campaign return and event controls.",
            Reusable: true,
            SearchTerms: ["season", "operations", "event"],
            EvidenceLines: ["Season operation receipt captured for checkpoint timing."],
            UpdatedAtUtc: DateTimeOffset.Parse("2026-04-03T00:00:00Z"));

        IReadOnlyList<string> compactPluralTokens = InvokeBuildTokens("seasonops");
        IReadOnlyList<string> compactSingularTokens = InvokeBuildTokens("seasonop");
        IReadOnlyList<string> negativeTokens = InvokeBuildTokens("matrixops");

        Assert.True(InvokeMatches(packet, compactPluralTokens));
        Assert.True(InvokeMatches(packet, compactSingularTokens));
        Assert.False(InvokeMatches(packet, negativeTokens));
    }

    [Fact]
    public void PrepLibraryQueryMatchingSupportsSeasonControlShorthandAcrossWhitespaceBoundaries()
    {
        var packet = new GovernedPrepPacketSummary(
            PacketId: "event:season-control",
            Kind: "event_control_packet",
            Title: "Dockyard season control board",
            Summary: "Season operations stay governed for the next launch window.",
            BindingSummary: "Bound to campaign return and event controls.",
            Reusable: true,
            SearchTerms: ["event", "control", "season", "operations"],
            EvidenceLines: ["Season control receipt captured for checkpoint timing."],
            UpdatedAtUtc: DateTimeOffset.Parse("2026-04-04T00:00:00Z"));

        IReadOnlyList<string> compactTokens = InvokeBuildTokens("seasoncontrol");
        IReadOnlyList<string> compactPluralTokens = InvokeBuildTokens("seasoncontrols");
        IReadOnlyList<string> compactAbbrevTokens = InvokeBuildTokens("seasonctrl");
        IReadOnlyList<string> compactCtlTokens = InvokeBuildTokens("seasonctl");
        IReadOnlyList<string> compactCtlPluralTokens = InvokeBuildTokens("seasonctls");
        IReadOnlyList<string> compactAbbrevPluralTokens = InvokeBuildTokens("seasonctrls");
        IReadOnlyList<string> negativeTokens = InvokeBuildTokens("matrixcontrol");

        Assert.True(InvokeMatches(packet, compactTokens));
        Assert.True(InvokeMatches(packet, compactPluralTokens));
        Assert.True(InvokeMatches(packet, compactAbbrevTokens));
        Assert.True(InvokeMatches(packet, compactCtlTokens));
        Assert.True(InvokeMatches(packet, compactCtlPluralTokens));
        Assert.True(InvokeMatches(packet, compactAbbrevPluralTokens));
        Assert.False(InvokeMatches(packet, negativeTokens));
    }

    [Fact]
    public void PrepLibraryQueryMatchingSupportsGmOpsShorthandAcrossWhitespaceBoundaries()
    {
        var packet = new GovernedPrepPacketSummary(
            PacketId: "event:gmops",
            Kind: "event_control_packet",
            Title: "Dockyard event control board",
            Summary: "Season operations stay governed for the next launch window.",
            BindingSummary: "Bound to campaign return and event controls.",
            Reusable: true,
            SearchTerms: ["event", "control", "season", "operations"],
            EvidenceLines: ["GM operations checkpoint receipt captured for event-control lane."],
            UpdatedAtUtc: DateTimeOffset.Parse("2026-04-04T00:00:00Z"));

        IReadOnlyList<string> compactPluralTokens = InvokeBuildTokens("gmops");
        IReadOnlyList<string> compactSingularTokens = InvokeBuildTokens("gmop");
        IReadOnlyList<string> compactOperationTokens = InvokeBuildTokens("gmoperation");
        IReadOnlyList<string> compactOperationsTokens = InvokeBuildTokens("gmoperations");
        IReadOnlyList<string> compactControlTokens = InvokeBuildTokens("gmcontrol");
        IReadOnlyList<string> compactControlsTokens = InvokeBuildTokens("gmcontrols");
        IReadOnlyList<string> compactCtrlTokens = InvokeBuildTokens("gmctrl");
        IReadOnlyList<string> compactCtlTokens = InvokeBuildTokens("gmctl");
        IReadOnlyList<string> negativeTokens = InvokeBuildTokens("gmatrix");

        Assert.True(InvokeMatches(packet, compactPluralTokens));
        Assert.True(InvokeMatches(packet, compactSingularTokens));
        Assert.True(InvokeMatches(packet, compactOperationTokens));
        Assert.True(InvokeMatches(packet, compactOperationsTokens));
        Assert.True(InvokeMatches(packet, compactControlTokens));
        Assert.True(InvokeMatches(packet, compactControlsTokens));
        Assert.True(InvokeMatches(packet, compactCtrlTokens));
        Assert.True(InvokeMatches(packet, compactCtlTokens));
        Assert.False(InvokeMatches(packet, negativeTokens));
    }

    [Fact]
    public void PrepLibraryQueryMatchingSupportsEventOpsShorthandAcrossWhitespaceBoundaries()
    {
        var packet = new GovernedPrepPacketSummary(
            PacketId: "event:eventops",
            Kind: "event_control_packet",
            Title: "Dockyard event control board",
            Summary: "Event operations stay governed for the next launch window.",
            BindingSummary: "Bound to campaign return and event controls.",
            Reusable: true,
            SearchTerms: ["event", "control", "operations"],
            EvidenceLines: ["Event operations checkpoint receipt captured for event-control lane."],
            UpdatedAtUtc: DateTimeOffset.Parse("2026-04-04T00:00:00Z"));

        IReadOnlyList<string> compactPluralTokens = InvokeBuildTokens("eventops");
        IReadOnlyList<string> compactSingularTokens = InvokeBuildTokens("eventop");
        IReadOnlyList<string> compactOperationTokens = InvokeBuildTokens("eventoperation");
        IReadOnlyList<string> compactOperationsTokens = InvokeBuildTokens("eventoperations");
        IReadOnlyList<string> negativeTokens = InvokeBuildTokens("matrixops");

        Assert.True(InvokeMatches(packet, compactPluralTokens));
        Assert.True(InvokeMatches(packet, compactSingularTokens));
        Assert.True(InvokeMatches(packet, compactOperationTokens));
        Assert.True(InvokeMatches(packet, compactOperationsTokens));
        Assert.False(InvokeMatches(packet, negativeTokens));
    }

    [Fact]
    public void PrepLibraryQueryMatchingSupportsSplitOpsAndControlShorthandAcrossWhitespaceAndPunctuation()
    {
        var packet = new GovernedPrepPacketSummary(
            PacketId: "event:split-ops",
            Kind: "event_control_packet",
            Title: "Dockyard event control board",
            Summary: "Season operations stay governed for the next launch window.",
            BindingSummary: "Bound to campaign return and event controls.",
            Reusable: true,
            SearchTerms: ["event", "control", "season", "operations"],
            EvidenceLines: ["GM operations checkpoint receipt captured for event-control lane."],
            UpdatedAtUtc: DateTimeOffset.Parse("2026-04-04T00:00:00Z"));

        Assert.True(InvokeMatches(packet, InvokeBuildTokens("event ops")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("event-ops")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("event operation")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("eventoperation")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("event-op")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("event-operation")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("event operations")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("eventoperations")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("event-operations")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("event control")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("event controls")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("event-control")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("event ctrl")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("event-ctrl")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("event ctls")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("event-ctls")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("event ctrls")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("event-ctrls")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("gm ops")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("gm-ops")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("gm operation")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("gm-operation")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("gm operations")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("gm-operations")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("gm control")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("gm-control")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("gm controls")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("gm-controls")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("gm ctrl")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("gm-ctrl")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("gm ctl")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("gm-ctl")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("gm ctls")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("gm-ctls")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("gm ctrls")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("gm-ctrls")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("season ops")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("season-ops")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("season operation")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("season-operation")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("season operations")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("season-operations")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("season control")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("season-control")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("season ctls")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("season-ctls")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("season ctrls")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("season-ctrls")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("leagueops")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("leagueop")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("league-op")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("leagueoperation")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("leagueoperations")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("league ops")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("league-ops")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("league operations")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("league-operations")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("league control")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("league controls")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("league-control")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("league-ctrl")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("leaguecontrol")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("leaguecontrols")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("leaguectrl")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("league ctl")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("league-ctl")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("league ctls")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("league-ctls")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("leaguectl")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("leaguectls")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("leaguectrls")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("communityops")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("communityop")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("community-op")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("communityoperation")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("communityoperations")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("community ops")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("community-ops")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("community operations")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("community-operations")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("community control")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("community controls")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("community-control")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("community-ctrl")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("communitycontrol")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("communitycontrols")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("communityctrl")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("community ctl")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("community-ctl")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("community ctls")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("community-ctls")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("communityctl")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("communityctls")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("communityctrls")));
    }

    [Fact]
    public void PrepLibraryQueryMatchingSupportsNextSessionReturnLoopShorthandAcrossWhitespaceAndPunctuation()
    {
        var packet = new GovernedPrepPacketSummary(
            PacketId: "return:next-session",
            Kind: "campaign_return_packet",
            Title: "Neon Cradle return-loop packet",
            Summary: "Next-session return loop stays governed from downtime through recap.",
            BindingSummary: "Bound to campaign return, memory timeline, and next-session carry-forward.",
            Reusable: true,
            SearchTerms: ["next", "session", "return", "loop", "downtime", "recap"],
            EvidenceLines: ["Next-session carry-forward keeps the return-loop lane reviewable."],
            UpdatedAtUtc: DateTimeOffset.Parse("2026-04-04T00:00:00Z"));

        Assert.True(InvokeMatches(packet, InvokeBuildTokens("nextsession")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("nextsessions")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("nextsessionreturn")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("nextsessionreturns")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("nextsessionreturnloop")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("nextsessionreturnloops")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("nextsessionloop")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("nextsessionloops")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("next-session")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("next-session-return")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("next session")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("next session return")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("sessionreturn")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("sessionreturns")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("sessionreturnloop")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("sessionreturnloops")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("session-return")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("session return")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("returnloop")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("returnloops")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("return-loop")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("return loop")));
        Assert.False(InvokeMatches(packet, InvokeBuildTokens("matrixloop")));
    }

    [Fact]
    public void PrepLibraryQueryMatchingSupportsSessionLogPluralShorthandAcrossWhitespaceAndPunctuation()
    {
        var packet = new GovernedPrepPacketSummary(
            PacketId: "diary:session-log",
            Kind: "campaign_diary_packet",
            Title: "Neon Cradle session log packet",
            Summary: "Session log continuity stays governed from diary through return.",
            BindingSummary: "Bound to campaign diary continuity and next-session return.",
            Reusable: true,
            SearchTerms: ["session", "log", "diary", "return"],
            EvidenceLines: ["Session log lane remains attached to governed continuity receipts."],
            UpdatedAtUtc: DateTimeOffset.Parse("2026-04-04T00:00:00Z"));

        Assert.True(InvokeMatches(packet, InvokeBuildTokens("sessionlog")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("sessionlogs")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("session log")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("session logs")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("session-log")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("session-logs")));
        Assert.False(InvokeMatches(packet, InvokeBuildTokens("matrixlogs")));
    }

    [Fact]
    public void PrepLibraryQueryMatchingSupportsContinuityPluralShorthandAcrossWhitespaceAndPunctuation()
    {
        var packet = new GovernedPrepPacketSummary(
            PacketId: "continuity:plural-lane",
            Kind: "campaign_continuity_packet",
            Title: "Neon Cradle diary downtime aftermath continuity packet",
            Summary: "Diary, downtime, aftermath, recap, return, memory, archive, history, timeline, ledger, lifestyle, license, SIN, heat, faction, connection, and relationship continuity remains governed for next-session return.",
            BindingSummary: "Bound to campaign diary continuity, downtime follow-through, aftermath recap, return cues, memory timeline, ledger history, lifestyle shifts, license posture, SIN handling, heat pressure, faction posture, and contact connection relationship changes.",
            Reusable: true,
            SearchTerms: ["diary", "journal", "downtime", "aftermath", "recap", "return", "memory", "archive", "history", "timeline", "ledger", "lifestyle", "license", "sin", "heat", "faction", "connection", "relationship"],
            EvidenceLines: ["Governed continuity lane keeps diary, downtime, aftermath, recap, return, memory, archive, history, timeline, ledger, lifestyle, license, SIN, heat, faction, connection, and relationship signals attached for next session."],
            UpdatedAtUtc: DateTimeOffset.Parse("2026-04-04T00:00:00Z"));

        Assert.True(InvokeMatches(packet, InvokeBuildTokens("diary")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("diaries")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("journal")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("journals")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("downtime")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("downtimes")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("aftermath")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("aftermaths")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("debrief")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("debriefs")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("debriefed")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("debriefing")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("debriefings")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("de brief")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("de briefs")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("de briefed")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("de briefing")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("de briefings")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("de-brief")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("de-briefs")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("de-briefed")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("de-briefing")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("de-briefings")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("outbrief")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("outbriefs")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("outbriefed")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("outbriefing")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("outbriefings")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("out brief")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("out briefs")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("out briefed")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("out briefing")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("out briefings")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("out-brief")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("out-briefs")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("out-briefed")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("out-briefing")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("out-briefings")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("postmortem")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("postmortems")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("post mortem")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("post mortems")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("post-mortem")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("post-mortems")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("postsession")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("postsessions")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("post session")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("post sessions")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("post-session")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("post-sessions")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("postrun")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("postruns")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("post run")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("post runs")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("post-run")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("post-runs")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("postgame")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("postgames")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("post game")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("post games")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("post-game")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("post-games")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("afteraction")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("afteractions")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("afteractionreport")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("afteractionreports")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("afteractionreview")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("afteractionreviews")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("after action")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("after actions")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("after action report")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("after action reports")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("after action review")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("after action reviews")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("after-action")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("after-actions")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("after-action report")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("after-action reports")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("after-action review")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("after-action reviews")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("aar")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("aars")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("retro")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("retros")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("retrospective")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("retrospectives")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("hotwash")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("hotwashes")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("hot wash")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("hot washes")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("hot-wash")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("hot-washes")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("lessonlearned")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("lessonslearned")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("lessonlearnt")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("lessonslearnt")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("lesson learned")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("lessons learned")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("lesson learnt")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("lessons learnt")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("lesson-learned")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("lessons-learned")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("lesson-learnt")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("lessons-learnt")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("recaps")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("returns")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("memories")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("archives")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("histories")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("timelines")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("ledgers")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("lifestyle")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("lifestyles")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("license")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("licenses")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("licences")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("sin")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("sins")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("heat")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("heats")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("faction")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("factions")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("contact")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("contacts")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("connection")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("connections")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("relationship")));
        Assert.True(InvokeMatches(packet, InvokeBuildTokens("relationships")));
        Assert.False(InvokeMatches(packet, InvokeBuildTokens("matrixaftermaths")));
        Assert.False(InvokeMatches(packet, InvokeBuildTokens("matrixafteraction")));
        Assert.False(InvokeMatches(packet, InvokeBuildTokens("matrixafteractionreport")));
        Assert.False(InvokeMatches(packet, InvokeBuildTokens("matrixafteractionreview")));
        Assert.False(InvokeMatches(packet, InvokeBuildTokens("matrixaar")));
        Assert.False(InvokeMatches(packet, InvokeBuildTokens("matrixretro")));
        Assert.False(InvokeMatches(packet, InvokeBuildTokens("matrixretrospective")));
        Assert.False(InvokeMatches(packet, InvokeBuildTokens("matrixoutbrief")));
        Assert.False(InvokeMatches(packet, InvokeBuildTokens("matrixoutbriefed")));
        Assert.False(InvokeMatches(packet, InvokeBuildTokens("matrixdebriefed")));
        Assert.False(InvokeMatches(packet, InvokeBuildTokens("matrixhotwash")));
        Assert.False(InvokeMatches(packet, InvokeBuildTokens("matrixlessonlearned")));
        Assert.False(InvokeMatches(packet, InvokeBuildTokens("matrixlessonlearnt")));
        Assert.False(InvokeMatches(packet, InvokeBuildTokens("matrixpostmortem")));
        Assert.False(InvokeMatches(packet, InvokeBuildTokens("matrixpostsession")));
        Assert.False(InvokeMatches(packet, InvokeBuildTokens("matrixpostrun")));
        Assert.False(InvokeMatches(packet, InvokeBuildTokens("matrixpostgame")));
    }

    [Fact]
    public void PrepLibraryQueryMatchingSupportsCrewTransferShorthandAcrossWhitespaceBoundaries()
    {
        var packet = new GovernedPrepPacketSummary(
            PacketId: "roster:compact",
            Kind: "roster_movement_packet",
            Title: "Neon Cradle roster movement packet",
            Summary: "Crew handoff remains governed for launch continuity.",
            BindingSummary: "Bound to campaign return and roster receipts.",
            Reusable: true,
            SearchTerms: ["crew", "handoff", "roster"],
            EvidenceLines: ["Crew handoff receipt captured for governed movement lane."],
            UpdatedAtUtc: DateTimeOffset.Parse("2026-04-03T00:00:00Z"));

        IReadOnlyList<string> compactTokens = InvokeBuildTokens("crewtransfer");
        IReadOnlyList<string> compactPluralTokens = InvokeBuildTokens("crewtransfers");
        IReadOnlyList<string> compactMoveTokens = InvokeBuildTokens("crewmove");
        IReadOnlyList<string> compactMovePluralTokens = InvokeBuildTokens("crewmoves");
        IReadOnlyList<string> compactShiftTokens = InvokeBuildTokens("crewshift");
        IReadOnlyList<string> compactShiftPluralTokens = InvokeBuildTokens("crewshifts");
        IReadOnlyList<string> compactSwapTokens = InvokeBuildTokens("crewswap");
        IReadOnlyList<string> compactSwapPluralTokens = InvokeBuildTokens("crewswaps");
        IReadOnlyList<string> compactMovementTokens = InvokeBuildTokens("crewmovement");
        IReadOnlyList<string> compactMovementPluralTokens = InvokeBuildTokens("crewmovements");
        IReadOnlyList<string> compactRosterSwapTokens = InvokeBuildTokens("rosterswap");
        IReadOnlyList<string> compactRosterSwapPluralTokens = InvokeBuildTokens("rosterswaps");
        IReadOnlyList<string> compactRosterShiftTokens = InvokeBuildTokens("rostershift");
        IReadOnlyList<string> compactRosterShiftPluralTokens = InvokeBuildTokens("rostershifts");
        IReadOnlyList<string> compactRosterMovePluralTokens = InvokeBuildTokens("rostermoves");
        IReadOnlyList<string> compactRosterMovementTokens = InvokeBuildTokens("rostermovement");
        IReadOnlyList<string> compactRosterMovementPluralTokens = InvokeBuildTokens("rostermovements");
        IReadOnlyList<string> hyphenCrewMoveTokens = InvokeBuildTokens("crew-move");
        IReadOnlyList<string> hyphenCrewMovementTokens = InvokeBuildTokens("crew-movement");
        IReadOnlyList<string> hyphenRosterMoveTokens = InvokeBuildTokens("roster-move");
        IReadOnlyList<string> hyphenRosterMovementTokens = InvokeBuildTokens("roster-movement");
        IReadOnlyList<string> splitCrewTransfersTokens = InvokeBuildTokens("crew transfers");
        IReadOnlyList<string> splitCrewTransferTokens = InvokeBuildTokens("crew transfer");
        IReadOnlyList<string> splitCrewHandoffsTokens = InvokeBuildTokens("crew handoffs");
        IReadOnlyList<string> splitCrewHandoffTokens = InvokeBuildTokens("crew handoff");
        IReadOnlyList<string> compactCrewHandoverTokens = InvokeBuildTokens("crewhandover");
        IReadOnlyList<string> compactCrewHandoversTokens = InvokeBuildTokens("crewhandovers");
        IReadOnlyList<string> splitCrewHandoverTokens = InvokeBuildTokens("crew handover");
        IReadOnlyList<string> splitCrewHandoversTokens = InvokeBuildTokens("crew handovers");
        IReadOnlyList<string> splitCrewMovesTokens = InvokeBuildTokens("crew moves");
        IReadOnlyList<string> splitCrewMoveTokens = InvokeBuildTokens("crew move");
        IReadOnlyList<string> splitCrewShiftsTokens = InvokeBuildTokens("crew shifts");
        IReadOnlyList<string> splitCrewShiftTokens = InvokeBuildTokens("crew shift");
        IReadOnlyList<string> splitCrewMovementTokens = InvokeBuildTokens("crew movement");
        IReadOnlyList<string> splitCrewMovementsTokens = InvokeBuildTokens("crew movements");
        IReadOnlyList<string> splitRosterTransfersTokens = InvokeBuildTokens("roster transfers");
        IReadOnlyList<string> splitRosterTransferTokens = InvokeBuildTokens("roster transfer");
        IReadOnlyList<string> splitRosterHandoffsTokens = InvokeBuildTokens("roster handoffs");
        IReadOnlyList<string> splitRosterHandoffTokens = InvokeBuildTokens("roster handoff");
        IReadOnlyList<string> compactRosterHandoverTokens = InvokeBuildTokens("rosterhandover");
        IReadOnlyList<string> compactRosterHandoversTokens = InvokeBuildTokens("rosterhandovers");
        IReadOnlyList<string> splitRosterHandoverTokens = InvokeBuildTokens("roster handover");
        IReadOnlyList<string> splitRosterHandoversTokens = InvokeBuildTokens("roster handovers");
        IReadOnlyList<string> splitRosterMovesTokens = InvokeBuildTokens("roster moves");
        IReadOnlyList<string> splitRosterMoveTokens = InvokeBuildTokens("roster move");
        IReadOnlyList<string> splitRosterShiftsTokens = InvokeBuildTokens("roster shifts");
        IReadOnlyList<string> splitRosterShiftTokens = InvokeBuildTokens("roster shift");
        IReadOnlyList<string> splitRosterMovementTokens = InvokeBuildTokens("roster movement");
        IReadOnlyList<string> splitRosterMovementsTokens = InvokeBuildTokens("roster movements");
        IReadOnlyList<string> negativeTokens = InvokeBuildTokens("matrixtransfer");

        Assert.True(InvokeMatches(packet, compactTokens));
        Assert.True(InvokeMatches(packet, compactPluralTokens));
        Assert.True(InvokeMatches(packet, compactMoveTokens));
        Assert.True(InvokeMatches(packet, compactMovePluralTokens));
        Assert.True(InvokeMatches(packet, compactShiftTokens));
        Assert.True(InvokeMatches(packet, compactShiftPluralTokens));
        Assert.True(InvokeMatches(packet, compactSwapTokens));
        Assert.True(InvokeMatches(packet, compactSwapPluralTokens));
        Assert.True(InvokeMatches(packet, compactMovementTokens));
        Assert.True(InvokeMatches(packet, compactMovementPluralTokens));
        Assert.True(InvokeMatches(packet, compactRosterSwapTokens));
        Assert.True(InvokeMatches(packet, compactRosterSwapPluralTokens));
        Assert.True(InvokeMatches(packet, compactRosterShiftTokens));
        Assert.True(InvokeMatches(packet, compactRosterShiftPluralTokens));
        Assert.True(InvokeMatches(packet, compactRosterMovePluralTokens));
        Assert.True(InvokeMatches(packet, compactRosterMovementTokens));
        Assert.True(InvokeMatches(packet, compactRosterMovementPluralTokens));
        Assert.True(InvokeMatches(packet, hyphenCrewMoveTokens));
        Assert.True(InvokeMatches(packet, hyphenCrewMovementTokens));
        Assert.True(InvokeMatches(packet, hyphenRosterMoveTokens));
        Assert.True(InvokeMatches(packet, hyphenRosterMovementTokens));
        Assert.True(InvokeMatches(packet, splitCrewTransfersTokens));
        Assert.True(InvokeMatches(packet, splitCrewTransferTokens));
        Assert.True(InvokeMatches(packet, splitCrewHandoffsTokens));
        Assert.True(InvokeMatches(packet, splitCrewHandoffTokens));
        Assert.True(InvokeMatches(packet, compactCrewHandoverTokens));
        Assert.True(InvokeMatches(packet, compactCrewHandoversTokens));
        Assert.True(InvokeMatches(packet, splitCrewHandoverTokens));
        Assert.True(InvokeMatches(packet, splitCrewHandoversTokens));
        Assert.True(InvokeMatches(packet, splitCrewMovesTokens));
        Assert.True(InvokeMatches(packet, splitCrewMoveTokens));
        Assert.True(InvokeMatches(packet, splitCrewShiftsTokens));
        Assert.True(InvokeMatches(packet, splitCrewShiftTokens));
        Assert.True(InvokeMatches(packet, splitCrewMovementTokens));
        Assert.True(InvokeMatches(packet, splitCrewMovementsTokens));
        Assert.True(InvokeMatches(packet, splitRosterTransfersTokens));
        Assert.True(InvokeMatches(packet, splitRosterTransferTokens));
        Assert.True(InvokeMatches(packet, splitRosterHandoffsTokens));
        Assert.True(InvokeMatches(packet, splitRosterHandoffTokens));
        Assert.True(InvokeMatches(packet, compactRosterHandoverTokens));
        Assert.True(InvokeMatches(packet, compactRosterHandoversTokens));
        Assert.True(InvokeMatches(packet, splitRosterHandoverTokens));
        Assert.True(InvokeMatches(packet, splitRosterHandoversTokens));
        Assert.True(InvokeMatches(packet, splitRosterMovesTokens));
        Assert.True(InvokeMatches(packet, splitRosterMoveTokens));
        Assert.True(InvokeMatches(packet, splitRosterShiftsTokens));
        Assert.True(InvokeMatches(packet, splitRosterShiftTokens));
        Assert.True(InvokeMatches(packet, splitRosterMovementTokens));
        Assert.True(InvokeMatches(packet, splitRosterMovementsTokens));
        Assert.False(InvokeMatches(packet, negativeTokens));
    }

    [Fact]
    public void ResolvePrepPacketNormalizesWhitespacePaddedPacketIds()
    {
        DateTimeOffset updatedAtUtc = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        var packet = new GovernedPrepPacketSummary(
            PacketId: "packet-1",
            Kind: "campaign_return_packet",
            Title: "Return packet",
            Summary: "Campaign return packet summary.",
            BindingSummary: "Binding summary",
            Reusable: true,
            SearchTerms: ["return"],
            EvidenceLines: ["evidence"],
            UpdatedAtUtc: updatedAtUtc);
        var prepLibrary = new CampaignPrepLibrarySummary(
            Summary: "summary",
            BindingSummary: "binding",
            SearchSummary: "search",
            ReusablePacketCount: 1,
            SearchablePacketCount: 1,
            Packets: [packet]);

        GovernedPrepPacketSummary resolved = InvokeResolvePrepPacket(prepLibrary, "  packet-1  ");

        Assert.Equal(packet.PacketId, resolved.PacketId);
    }

    [Fact]
    public void ResolveTravelPrefetchDeviceNormalizesWhitespacePaddedInstallationIds()
    {
        WorkspaceRestoreProjection restore = BuildEmptyRestore() with
        {
            ClaimedDevices =
            [
                new ClaimedDeviceRestoreProjection(
                    InstallationId: "install-1",
                    DeviceRole: "travel_cache",
                    Platform: "windows",
                    HeadId: "avalonia",
                    Channel: "stable",
                    HostLabel: "travel-kit",
                    RestoreSummary: "Device restore summary")
            ]
        };

        ClaimedDeviceRestoreProjection resolved = InvokeResolveTravelPrefetchDevice(restore, "  install-1  ");

        Assert.Equal("install-1", resolved.InstallationId);
    }

    [Fact]
    public void BoundedRecapShelfCategoryDoesNotActivateFromRecapitalizationKindWithoutRecapIdentity()
    {
        PublicationSafeProjection publication = BuildPublicationSafeProjection("recapitalization_signal");

        string category = InvokeBoundedRecapShelfCategory(publication);

        Assert.Equal("other", category);
    }

    [Fact]
    public void SupportsCreatorShelfProjectionDoesNotActivateFromAfterburnerCampaignerRunboardwalkWithoutTokenIdentity()
    {
        PublicationSafeProjection publication = BuildPublicationSafeProjection("afterburner_campaigner_runboardwalk");

        bool supported = InvokeSupportsCreatorShelfProjection(publication);

        Assert.False(supported);
    }

    [Fact]
    public void BoundedRecapShelfCategoryKeepsCampaignRecapBundleClassification()
    {
        PublicationSafeProjection publication = BuildPublicationSafeProjection("campaign_recap_bundle");

        string category = InvokeBoundedRecapShelfCategory(publication);
        bool supported = InvokeSupportsCreatorShelfProjection(publication);

        Assert.Equal("campaign", category);
        Assert.True(supported);
    }

    [Theory]
    [InlineData("debriefed")]
    [InlineData("debriefing")]
    [InlineData("debriefings")]
    [InlineData("de-briefing")]
    [InlineData("post-session")]
    [InlineData("post-run")]
    [InlineData("post-game")]
    [InlineData("afteraction")]
    [InlineData("afteractions")]
    [InlineData("aar")]
    [InlineData("aars")]
    [InlineData("retro")]
    [InlineData("retrospectives")]
    [InlineData("afteractionreview")]
    public void BoundedRecapShelfCategoryTreatsContinuityRecapShorthandKindsAsAftermath(string kind)
    {
        PublicationSafeProjection publication = BuildPublicationSafeProjection(kind);

        string category = InvokeBoundedRecapShelfCategory(publication);
        bool supported = InvokeSupportsCreatorShelfProjection(publication);

        Assert.Equal("aftermath", category);
        Assert.True(supported);
    }

    [Fact]
    public void BoundedRecapShelfCategoryKeepsDowntimeClassification()
    {
        PublicationSafeProjection publication = BuildPublicationSafeProjection("downtime");

        string category = InvokeBoundedRecapShelfCategory(publication);
        bool supported = InvokeSupportsCreatorShelfProjection(publication);

        Assert.Equal("downtime", category);
        Assert.True(supported);
    }

    [Fact]
    public void PrepLibraryIncludesRosterMovementPacketWhenRosterTransfersExist()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithRosterAndAftermath();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "roster_movement_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("roster", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains("movement", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
    }

    [Fact]
    public void PrepLibraryIncludesAftermathPacketWhenAftermathPackagesExist()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithRosterAndAftermath();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "aftermath_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("aftermath", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains("downtime", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
    }

    [Fact]
    public void PrepLibraryIncludesCampaignMemoryPacketWhenWorkspaceMemoryExists()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithCampaignMemorySignals();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "campaign_memory_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("memory", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains("archive", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains("history", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains("timeline", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains("ledger", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("long-lived memory", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("memory ledger", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void CampaignWorkspaceSummaryDeduplicatesIdenticalPublicationFamilies_WhenPayloadRepeatsSameRows()
    {
        CampaignWorkspaceProjection seed = BuildWorkspaceWithRosterAndAftermath();
        RosterTransferProjection transfer = Assert.Single(seed.RosterTransfers ?? Array.Empty<RosterTransferProjection>());
        PublicationSafeProjection recap = new(
            ProjectionId: "recap-1",
            Kind: "campaign_recap_bundle",
            Label: "Session recap",
            Summary: "Recap-safe output remains attached to campaign continuity.");
        CampaignConsequenceProjection consequence = new(
            ConsequenceId: "consequence-1",
            Kind: "heat_pressure_lane",
            Label: "Heat pressure lane",
            State: "active",
            Summary: "Heat pressure remains attached to campaign continuity.",
            EvidenceLines: [],
            Receipts: [],
            UpdatedAtUtc: DateTimeOffset.Parse("2026-04-03T00:00:00Z"));
        CampaignWorkspaceProjection workspace = seed with
        {
            RecapShelf = [recap, recap],
            Consequences = [consequence, consequence],
            RosterTransfers = [transfer, transfer]
        };
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        CampaignWorkspaceSummary summary = InvokeBuildCampaignWorkspaceSummary(workspace, restore);

        Assert.Contains("1 publication-safe output(s)", summary.PublicationSummary, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("1 governed consequence signal(s)", summary.PublicationSummary, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("1 roster-transfer receipt(s)", summary.PublicationSummary, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void CampaignWorkspaceSummaryDeduplicatesSemanticallyIdenticalRecapRows_WhenProjectionIdsDiffer()
    {
        CampaignWorkspaceProjection seed = BuildWorkspaceWithRosterAndAftermath();
        PublicationSafeProjection recapA = new(
            ProjectionId: "recap-semantic-a",
            Kind: "campaign_recap_bundle",
            Label: "Session recap",
            Summary: "Recap-safe output remains attached to campaign continuity.");
        PublicationSafeProjection recapB = recapA with
        {
            ProjectionId = "recap-semantic-b"
        };
        CampaignWorkspaceProjection workspace = seed with
        {
            RecapShelf = [recapA, recapB]
        };
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        CampaignWorkspaceSummary summary = InvokeBuildCampaignWorkspaceSummary(workspace, restore);

        Assert.Contains("1 publication-safe output(s)", summary.PublicationSummary, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void CampaignWorkspaceSummaryDeduplicatesSemanticallyIdenticalRecapRows_WhenArtifactAndPublicationIdsDiffer()
    {
        CampaignWorkspaceProjection seed = BuildWorkspaceWithRosterAndAftermath();
        PublicationSafeProjection recapA = new(
            ProjectionId: "recap-semantic-a",
            Kind: "campaign_recap_bundle",
            Label: "Session recap",
            Summary: "Recap-safe output remains attached to campaign continuity.",
            ArtifactId: "artifact-a",
            CreatorPublicationId: "publication-a");
        PublicationSafeProjection recapB = recapA with
        {
            ProjectionId = "recap-semantic-b",
            ArtifactId = "artifact-b",
            CreatorPublicationId = "publication-b"
        };
        CampaignWorkspaceProjection workspace = seed with
        {
            RecapShelf = [recapA, recapB]
        };
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        CampaignWorkspaceSummary summary = InvokeBuildCampaignWorkspaceSummary(workspace, restore);

        Assert.Contains("1 publication-safe output(s)", summary.PublicationSummary, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void CampaignWorkspaceSummaryDeduplicatesSemanticallyIdenticalRosterTransfers_WhenTransferIdsDiffer()
    {
        CampaignWorkspaceProjection seed = BuildWorkspaceWithRosterAndAftermath();
        RosterTransferProjection transfer = Assert.Single(seed.RosterTransfers ?? Array.Empty<RosterTransferProjection>());
        RosterTransferProjection duplicateWithDifferentId = transfer with
        {
            TransferId = "transfer-semantic-dup"
        };
        CampaignWorkspaceProjection workspace = seed with
        {
            RosterTransfers = [transfer, duplicateWithDifferentId]
        };
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        CampaignWorkspaceSummary summary = InvokeBuildCampaignWorkspaceSummary(workspace, restore);

        Assert.Contains("1 roster-transfer receipt(s)", summary.PublicationSummary, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void CampaignWorkspaceSummarySessionReadinessPrefersAttentionCueOverEarlierReviewCue()
    {
        CampaignWorkspaceProjection seed = BuildWorkspaceWithRosterAndAftermath();
        CampaignReadinessCue reviewCue = new(
            CueId: "cue-review-1",
            Severity: "review",
            Title: "Rule environment review",
            Summary: "Ruleset should be reviewed.");
        CampaignReadinessCue attentionCue = new(
            CueId: "cue-attention-1",
            Severity: "attention",
            Title: "Open objective pressure",
            Summary: "Objective pressure remains high.");
        CampaignWorkspaceProjection workspace = seed with
        {
            ReadinessCues = [reviewCue, attentionCue]
        };
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        CampaignWorkspaceSummary summary = InvokeBuildCampaignWorkspaceSummary(workspace, restore);

        Assert.Equal("Open objective pressure: Objective pressure remains high.", summary.SessionReadinessSummary);
        Assert.DoesNotContain("Rule environment review", summary.SessionReadinessSummary, StringComparison.Ordinal);
    }

    [Fact]
    public void CampaignWorkspaceSummarySessionReadinessPrefersWarningCueOverEarlierReviewCue()
    {
        CampaignWorkspaceProjection seed = BuildWorkspaceWithRosterAndAftermath();
        CampaignReadinessCue reviewCue = new(
            CueId: "cue-review-1",
            Severity: "review",
            Title: "Rule environment review",
            Summary: "Ruleset should be reviewed.");
        CampaignReadinessCue warningCue = new(
            CueId: "cue-warning-1",
            Severity: "warning",
            Title: "Continuity gap detected",
            Summary: "At least one dossier is missing continuity.");
        CampaignWorkspaceProjection workspace = seed with
        {
            ReadinessCues = [reviewCue, warningCue]
        };
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        CampaignWorkspaceSummary summary = InvokeBuildCampaignWorkspaceSummary(workspace, restore);

        Assert.Equal("Continuity gap detected: At least one dossier is missing continuity.", summary.SessionReadinessSummary);
        Assert.DoesNotContain("Rule environment review", summary.SessionReadinessSummary, StringComparison.Ordinal);
    }

    [Fact]
    public void RosterReadinessHighlightsPreferAttentionCueOverEarlierReviewCue()
    {
        CampaignWorkspaceProjection seed = BuildWorkspaceWithRosterAndAftermath();
        CampaignReadinessCue reviewCue = new(
            CueId: "cue-review-1",
            Severity: "review",
            Title: "Rule environment review",
            Summary: "Ruleset should be reviewed.");
        CampaignReadinessCue attentionCue = new(
            CueId: "cue-attention-1",
            Severity: "attention",
            Title: "Open objective pressure",
            Summary: "Objective pressure remains high.");
        CampaignWorkspaceProjection workspace = seed with
        {
            ReadinessCues = [reviewCue, attentionCue]
        };

        RosterReadinessSummary summary = InvokeBuildRosterReadinessSummary(workspace);

        string highlight = Assert.IsType<string>(summary.Highlights.FirstOrDefault());
        Assert.Contains("Open objective pressure", highlight, StringComparison.Ordinal);
    }

    [Fact]
    public void CampaignSpineGroupSeasonBoardEntryWatchoutPrefersAttentionCueOverEarlierReviewCue()
    {
        CampaignWorkspaceProjection seed = BuildWorkspaceWithRosterAndAftermath();
        CampaignReadinessCue reviewCue = new(
            CueId: "cue-review-1",
            Severity: "review",
            Title: "Rule environment review",
            Summary: "Ruleset should be reviewed.");
        CampaignReadinessCue attentionCue = new(
            CueId: "cue-attention-1",
            Severity: "attention",
            Title: "Open objective pressure",
            Summary: "Objective pressure remains high.");
        CampaignWorkspaceProjection workspace = seed with
        {
            ReadinessCues = [reviewCue, attentionCue]
        };

        IReadOnlyList<CommunitySeasonBoardEntryProjection> entries = InvokeCampaignSpineBuildGroupSeasonBoardEntries([workspace]);

        CommunitySeasonBoardEntryProjection entry = Assert.Single(entries);
        Assert.Contains("Open objective pressure", entry.WatchoutSummary, StringComparison.Ordinal);
        Assert.DoesNotContain("Rule environment review", entry.WatchoutSummary, StringComparison.Ordinal);
    }

    [Fact]
    public void CampaignSpineGroupSeasonBoardEntryWatchoutPrefersWarningCueOverEarlierReviewCue()
    {
        CampaignWorkspaceProjection seed = BuildWorkspaceWithRosterAndAftermath();
        CampaignReadinessCue reviewCue = new(
            CueId: "cue-review-1",
            Severity: "review",
            Title: "Rule environment review",
            Summary: "Ruleset should be reviewed.");
        CampaignReadinessCue warningCue = new(
            CueId: "cue-warning-1",
            Severity: "warning",
            Title: "Continuity gap detected",
            Summary: "At least one dossier is missing continuity.");
        CampaignWorkspaceProjection workspace = seed with
        {
            ReadinessCues = [reviewCue, warningCue]
        };

        IReadOnlyList<CommunitySeasonBoardEntryProjection> entries = InvokeCampaignSpineBuildGroupSeasonBoardEntries([workspace]);

        CommunitySeasonBoardEntryProjection entry = Assert.Single(entries);
        Assert.Contains("Continuity gap detected", entry.WatchoutSummary, StringComparison.Ordinal);
        Assert.DoesNotContain("Rule environment review", entry.WatchoutSummary, StringComparison.Ordinal);
    }

    [Fact]
    public void CampaignSpineGroupOperatorWatchoutsPrioritizeAttentionBeforeReviewWhenLimited()
    {
        CampaignWorkspaceProjection seed = BuildWorkspaceWithRosterAndAftermath();
        CampaignWorkspaceProjection reviewHeavyWorkspace = seed with
        {
            CampaignName = "Review lane",
            ReadinessCues =
            [
                new CampaignReadinessCue("cue-review-1", "review", "Rule environment review", "Ruleset should be reviewed."),
                new CampaignReadinessCue("cue-review-2", "review", "Crew roster review", "Crew roster requires review."),
                new CampaignReadinessCue("cue-review-3", "review", "Offline cache review", "Offline cache should be reviewed."),
                new CampaignReadinessCue("cue-review-4", "review", "Recap shelf review", "Recap shelf should be reviewed.")
            ]
        };
        CampaignWorkspaceProjection attentionWorkspace = seed with
        {
            CampaignName = "Attention lane",
            ReadinessCues =
            [
                new CampaignReadinessCue("cue-attention-1", "attention", "Open objective pressure", "Objective pressure remains high.")
            ]
        };

        IReadOnlyList<string> watchouts = InvokeCampaignSpineBuildGroupOperatorWatchouts([reviewHeavyWorkspace, attentionWorkspace]);

        Assert.Equal(4, watchouts.Count);
        Assert.Contains("Attention lane: Open objective pressure — Objective pressure remains high.", watchouts, StringComparer.Ordinal);
    }

    [Fact]
    public void CampaignSpineWorkspaceDigestWatchoutsPreferAttentionCueOverEarlierReviewCue()
    {
        CampaignWorkspaceProjection seed = BuildWorkspaceWithRosterAndAftermath();
        CampaignWorkspaceProjection workspace = seed with
        {
            ReadinessCues =
            [
                new CampaignReadinessCue("cue-review-1", "review", "Rule environment review", "Ruleset should be reviewed."),
                new CampaignReadinessCue("cue-attention-1", "attention", "Open objective pressure", "Objective pressure remains high.")
            ]
        };
        AccountCampaignSummary summary = new(
            Dossiers: [],
            Campaigns: [],
            Runs: [],
            Crews: [],
            Workspaces: [workspace],
            CommunityOperations: [],
            BuildLabHandoffs: [],
            RulesNavigator: [],
            MigrationReceipts: [],
            CreatorPublications: [],
            Restore: BuildEmptyRestore());

        CampaignWorkspaceDigestProjection digest = InvokeCampaignSpineBuildWorkspaceDigest(summary, workspace);

        string watchout = Assert.IsType<string>(digest.Watchouts.FirstOrDefault());
        Assert.Contains("Open objective pressure", watchout, StringComparison.Ordinal);
        Assert.DoesNotContain("Rule environment review", watchout, StringComparison.Ordinal);
    }

    [Fact]
    public void CampaignSpineWorkspaceDigestWatchoutsPreferWarningCueOverEarlierReviewCue()
    {
        CampaignWorkspaceProjection seed = BuildWorkspaceWithRosterAndAftermath();
        CampaignWorkspaceProjection workspace = seed with
        {
            ReadinessCues =
            [
                new CampaignReadinessCue("cue-review-1", "review", "Rule environment review", "Ruleset should be reviewed."),
                new CampaignReadinessCue("cue-warning-1", "warning", "Continuity gap detected", "At least one dossier is missing continuity.")
            ]
        };
        AccountCampaignSummary summary = new(
            Dossiers: [],
            Campaigns: [],
            Runs: [],
            Crews: [],
            Workspaces: [workspace],
            CommunityOperations: [],
            BuildLabHandoffs: [],
            RulesNavigator: [],
            MigrationReceipts: [],
            CreatorPublications: [],
            Restore: BuildEmptyRestore());

        CampaignWorkspaceDigestProjection digest = InvokeCampaignSpineBuildWorkspaceDigest(summary, workspace);

        string watchout = Assert.IsType<string>(digest.Watchouts.FirstOrDefault());
        Assert.Contains("Continuity gap detected", watchout, StringComparison.Ordinal);
        Assert.DoesNotContain("Rule environment review", watchout, StringComparison.Ordinal);
    }

    [Fact]
    public void WorkspaceStateSummaryPrefersAttentionContinuityConflictOverEarlierReviewConflict()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithRosterAndAftermath();
        var reviewConflict = new ContinuityConflictCue(
            CueId: "conflict-review-1",
            Severity: "review",
            Summary: "Review continuity note.",
            ResolutionAction: "Review roster notes.");
        var attentionConflict = new ContinuityConflictCue(
            CueId: "conflict-attention-1",
            Severity: "attention",
            Summary: "Active continuity conflict needs immediate reconciliation.",
            ResolutionAction: "Resolve restore ownership mismatch.");

        WorkspaceStateSummary summary = InvokeBuildWorkspaceStateSummary(
            workspace,
            ruleEnvironmentHealth: [],
            continuityConflicts: [reviewConflict, attentionConflict],
            supportDigests: [],
            travelMode: BuildTravelModeReadinessSummary(),
            nextSafeAction: InvokeBuildNextSafeActionCue(workspace));

        Assert.Equal("restore_conflict_present", summary.Status);
        Assert.Contains("Active continuity conflict needs immediate reconciliation.", summary.Summary, StringComparison.Ordinal);
        Assert.DoesNotContain("Review continuity note.", summary.Summary, StringComparison.Ordinal);
    }

    [Fact]
    public void WorkspaceStateSummaryPrefersWarningRuleCueOverEarlierReviewCue()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithRosterAndAftermath();
        var reviewRuleCue = new RuleEnvironmentHealthCue(
            EnvironmentId: "env-1",
            Severity: "review",
            Title: "Rule environment review",
            Summary: "Ruleset should be reviewed.");
        var warningRuleCue = new RuleEnvironmentHealthCue(
            EnvironmentId: "env-1",
            Severity: "warning",
            Title: "Rule mismatch warning",
            Summary: "One runner uses a stale compatibility fingerprint.");

        WorkspaceStateSummary summary = InvokeBuildWorkspaceStateSummary(
            workspace,
            ruleEnvironmentHealth: [reviewRuleCue, warningRuleCue],
            continuityConflicts: [],
            supportDigests: [],
            travelMode: BuildTravelModeReadinessSummary(),
            nextSafeAction: InvokeBuildNextSafeActionCue(workspace));

        Assert.Equal("rule_environment_mismatch", summary.Status);
        Assert.Contains("One runner uses a stale compatibility fingerprint.", summary.Summary, StringComparison.Ordinal);
        Assert.DoesNotContain("Ruleset should be reviewed.", summary.Summary, StringComparison.Ordinal);
    }

    [Fact]
    public void DecisionNoticesPreferReporterActionSupportCaseOverEarlierNonActionCase()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithRosterAndAftermath();
        CampaignWorkspaceDigestProjection digest = BuildWorkspaceDigest(workspace);
        CampaignPrepLibrarySummary prepLibrary = BuildEmptyPrepLibrary();
        SupportCaseDigestViewModel informationalCase = BuildSupportCaseDigest(
            caseId: "case-info",
            releaseProgressSummary: "Informational support case is tracking in the background.");
        SupportCaseDigestViewModel reporterActionCase = BuildSupportCaseDigest(
            caseId: "case-reporter-action",
            releaseProgressSummary: "Reporter action support case needs immediate follow-through.",
            reporterActionNeeded: true);

        IReadOnlyList<DecisionNotice> notices = InvokeBuildDecisionNotices(
            workspace,
            digest,
            [informationalCase, reporterActionCase],
            prepLibrary);

        DecisionNotice supportNotice = Assert.Single(notices, notice => string.Equals(notice.Kind, "support_follow_through", StringComparison.Ordinal));
        Assert.Contains("Reporter action support case needs immediate follow-through.", supportNotice.Summary, StringComparison.Ordinal);
    }

    [Fact]
    public void DecisionNoticesPreferCanVerifySupportCaseOverEarlierNonActionCase()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithRosterAndAftermath();
        CampaignWorkspaceDigestProjection digest = BuildWorkspaceDigest(workspace);
        CampaignPrepLibrarySummary prepLibrary = BuildEmptyPrepLibrary();
        SupportCaseDigestViewModel informationalCase = BuildSupportCaseDigest(
            caseId: "case-info",
            releaseProgressSummary: "Informational support case is tracking in the background.");
        SupportCaseDigestViewModel canVerifyCase = BuildSupportCaseDigest(
            caseId: "case-can-verify",
            releaseProgressSummary: "Fix-verify support case is ready for user confirmation.",
            canVerifyFix: true);

        IReadOnlyList<DecisionNotice> notices = InvokeBuildDecisionNotices(
            workspace,
            digest,
            [informationalCase, canVerifyCase],
            prepLibrary);

        DecisionNotice supportNotice = Assert.Single(notices, notice => string.Equals(notice.Kind, "support_follow_through", StringComparison.Ordinal));
        Assert.Contains("Fix-verify support case is ready for user confirmation.", supportNotice.Summary, StringComparison.Ordinal);
    }

    [Fact]
    public void SupportClosuresPreferReporterActionCaseOverEarlierNonActionCase()
    {
        SupportCaseDigestViewModel informationalCase = BuildSupportCaseDigest(
            caseId: "case-info",
            releaseProgressSummary: "Informational support case is tracking in the background.");
        SupportCaseDigestViewModel reporterActionCase = BuildSupportCaseDigest(
            caseId: "case-reporter-action",
            releaseProgressSummary: "Reporter action support case needs immediate follow-through.",
            reporterActionNeeded: true);

        IReadOnlyList<SupportClosureCue> closures = InvokeBuildSupportClosures([informationalCase, reporterActionCase]);

        SupportClosureCue lead = Assert.IsType<SupportClosureCue>(closures.FirstOrDefault());
        Assert.Equal("case-reporter-action", lead.CaseId);
    }

    [Fact]
    public void KnownIssuesPreferReporterActionCaseOverEarlierCanVerifyCase()
    {
        SupportCaseDigestViewModel canVerifyCase = BuildSupportCaseDigest(
            caseId: "case-can-verify",
            releaseProgressSummary: "Fix-verify support case is ready for user confirmation.",
            canVerifyFix: true);
        SupportCaseDigestViewModel reporterActionCase = BuildSupportCaseDigest(
            caseId: "case-reporter-action",
            releaseProgressSummary: "Reporter action support case needs immediate follow-through.",
            reporterActionNeeded: true);

        IReadOnlyList<KnownIssueAffectingInstall> issues = InvokeBuildKnownIssues([canVerifyCase, reporterActionCase]);

        KnownIssueAffectingInstall lead = Assert.IsType<KnownIssueAffectingInstall>(issues.FirstOrDefault());
        Assert.Equal("case-reporter-action", lead.CaseId);
        Assert.Equal("attention", lead.Severity);
        Assert.Equal("warning", Assert.IsType<KnownIssueAffectingInstall>(issues[1]).Severity);
    }

    [Fact]
    public void RecapShelfDeduplicatesSemanticallyIdenticalRows_WhenProjectionIdsDiffer()
    {
        CampaignWorkspaceProjection seed = BuildWorkspaceWithRosterAndAftermath();
        PublicationSafeProjection recapA = new(
            ProjectionId: "recap-semantic-a",
            Kind: "campaign_recap_bundle",
            Label: "Session recap",
            Summary: "Recap-safe output remains attached to campaign continuity.");
        PublicationSafeProjection recapB = recapA with
        {
            ProjectionId = "recap-semantic-b"
        };
        PublicationSafeProjection downtime = new(
            ProjectionId: "downtime-1",
            Kind: "downtime_brief",
            Label: "Downtime brief",
            Summary: "Downtime consequences are pinned to the same continuity lane.");
        CampaignWorkspaceProjection workspace = seed with
        {
            RecapShelf = [recapA, recapB, downtime]
        };

        IReadOnlyList<RecapShelfEntry> shelf = InvokeBuildRecapShelf(workspace);

        Assert.Equal(2, shelf.Count);
        Assert.Single(shelf, item => string.Equals(item.Label, "Session recap", StringComparison.Ordinal));
        Assert.Single(shelf, item => string.Equals(item.Label, "Downtime brief", StringComparison.Ordinal));
    }

    [Fact]
    public void RecapShelfUsesLatestAftermathTimestamp_WhenAftermathPackageIdsRepeat()
    {
        CampaignWorkspaceProjection seed = BuildWorkspaceWithRosterAndAftermath();
        DateTimeOffset earlier = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        DateTimeOffset later = earlier.AddMinutes(15);
        PublicationSafeProjection recap = new(
            ProjectionId: "package-duplicate",
            Kind: "downtime_brief",
            Label: "Downtime brief",
            Summary: "Downtime continuity recap.");
        AftermathRecapPackageProjection packageEarlier = new(
            PackageId: "package-duplicate",
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            RunId: "run-1",
            RunTitle: "Dockyard pressure test",
            PackageKind: "downtime_brief",
            Title: "Downtime brief",
            Summary: "Earlier package projection.",
            ArtifactId: "artifact-1",
            EvidenceLines: ["Earlier timeline evidence."],
            InitiatedByUserId: "gm-1",
            GeneratedAtUtc: earlier);
        AftermathRecapPackageProjection packageLater = packageEarlier with
        {
            GeneratedAtUtc = later,
            ArtifactId = "artifact-2",
            Summary = "Later package projection."
        };
        CampaignWorkspaceProjection workspace = seed with
        {
            RecapShelf = [recap],
            AftermathPackages = [packageEarlier, packageLater]
        };

        IReadOnlyList<RecapShelfEntry> shelf = InvokeBuildRecapShelf(workspace);

        RecapShelfEntry entry = Assert.Single(shelf);
        Assert.Equal("Downtime brief", entry.Label);
        Assert.Equal(later, entry.UpdatedAtUtc);
    }

    [Fact]
    public void RecapShelfUsesLatestAftermathTimestamp_WhenRecapProjectionIdHasWhitespacePadding()
    {
        CampaignWorkspaceProjection seed = BuildWorkspaceWithRosterAndAftermath();
        DateTimeOffset earlier = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        DateTimeOffset later = earlier.AddMinutes(15);
        PublicationSafeProjection recap = new(
            ProjectionId: "  package-duplicate  ",
            Kind: "downtime_brief",
            Label: "Downtime brief",
            Summary: "Downtime continuity recap.");
        AftermathRecapPackageProjection packageEarlier = new(
            PackageId: "package-duplicate",
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            RunId: "run-1",
            RunTitle: "Dockyard pressure test",
            PackageKind: "downtime_brief",
            Title: "Downtime brief",
            Summary: "Earlier package projection.",
            ArtifactId: "artifact-1",
            EvidenceLines: ["Earlier timeline evidence."],
            InitiatedByUserId: "gm-1",
            GeneratedAtUtc: earlier);
        AftermathRecapPackageProjection packageLater = packageEarlier with
        {
            GeneratedAtUtc = later,
            ArtifactId = "artifact-2",
            Summary = "Later package projection."
        };
        CampaignWorkspaceProjection workspace = seed with
        {
            RecapShelf = [recap],
            AftermathPackages = [packageEarlier, packageLater]
        };

        IReadOnlyList<RecapShelfEntry> shelf = InvokeBuildRecapShelf(workspace);

        RecapShelfEntry entry = Assert.Single(shelf);
        Assert.Equal("Downtime brief", entry.Label);
        Assert.Equal(later, entry.UpdatedAtUtc);
    }

    [Fact]
    public void RecapShelfUsesLatestCreatorPublication_WhenPublicationIdsRepeat()
    {
        CampaignWorkspaceProjection seed = BuildWorkspaceWithRosterAndAftermath();
        PublicationSafeProjection recap = new(
            ProjectionId: "recap-publication-1",
            Kind: "campaign_recap_bundle",
            Label: "Session recap",
            Summary: "Recap-safe output remains attached to campaign continuity.",
            CreatorPublicationId: "pub-duplicate");
        CreatorPublicationProjection older = new(
            PublicationId: "pub-duplicate",
            Title: "Session recap older projection",
            Kind: "campaign_recap_bundle",
            Summary: "Older publication row.",
            CampaignId: "campaign-a",
            DossierId: null,
            ArtifactId: "artifact-old",
            ProvenanceSummary: "Older provenance",
            DiscoverySummary: "Older discovery",
            Visibility: "group",
            PublicationStatus: "review",
            TrustBand: "bounded",
            Discoverable: false,
            UpdatedAtUtc: DateTimeOffset.Parse("2026-04-03T00:00:00Z"));
        CreatorPublicationProjection newer = older with
        {
            ArtifactId = "artifact-new",
            PublicationStatus = "published",
            TrustBand = "verified",
            Discoverable = true,
            UpdatedAtUtc = DateTimeOffset.Parse("2026-04-03T00:10:00Z")
        };
        CampaignWorkspaceProjection workspace = seed with
        {
            RecapShelf = [recap]
        };

        IReadOnlyList<RecapShelfEntry> shelf = InvokeBuildRecapShelf(workspace, [older, newer]);

        RecapShelfEntry entry = Assert.Single(shelf);
        Assert.Equal("pub-duplicate", entry.CreatorPublicationId);
        Assert.Equal("published", entry.PublicationState);
        Assert.Equal("verified", entry.TrustBand);
        Assert.True(entry.Discoverable);
    }

    [Fact]
    public void RecapShelfUsesLatestCreatorPublication_WhenRecapPublicationIdHasWhitespacePadding()
    {
        CampaignWorkspaceProjection seed = BuildWorkspaceWithRosterAndAftermath();
        PublicationSafeProjection recap = new(
            ProjectionId: "recap-publication-whitespace-1",
            Kind: "campaign_recap_bundle",
            Label: "Session recap",
            Summary: "Recap-safe output remains attached to campaign continuity.",
            CreatorPublicationId: "  pub-duplicate  ");
        CreatorPublicationProjection older = new(
            PublicationId: "pub-duplicate",
            Title: "Session recap older projection",
            Kind: "campaign_recap_bundle",
            Summary: "Older publication row.",
            CampaignId: "campaign-a",
            DossierId: null,
            ArtifactId: "artifact-old",
            ProvenanceSummary: "Older provenance",
            DiscoverySummary: "Older discovery",
            Visibility: "group",
            PublicationStatus: "review",
            TrustBand: "bounded",
            Discoverable: false,
            UpdatedAtUtc: DateTimeOffset.Parse("2026-04-03T00:00:00Z"));
        CreatorPublicationProjection newer = older with
        {
            ArtifactId = "artifact-new",
            PublicationStatus = "published",
            TrustBand = "verified",
            Discoverable = true,
            UpdatedAtUtc = DateTimeOffset.Parse("2026-04-03T00:10:00Z")
        };
        CampaignWorkspaceProjection workspace = seed with
        {
            RecapShelf = [recap]
        };

        IReadOnlyList<RecapShelfEntry> shelf = InvokeBuildRecapShelf(workspace, [older, newer]);

        RecapShelfEntry entry = Assert.Single(shelf);
        Assert.Equal("pub-duplicate", entry.CreatorPublicationId);
        Assert.Equal("published", entry.PublicationState);
        Assert.Equal("verified", entry.TrustBand);
        Assert.True(entry.Discoverable);
    }

    [Fact]
    public void CampaignSpineAttachCreatorPublicationPostureUsesLatestPublication_WhenPublicationIdsRepeat()
    {
        CampaignWorkspaceProjection seed = BuildWorkspaceWithRosterAndAftermath();
        PublicationSafeProjection recap = new(
            ProjectionId: "recap-publication-attach-1",
            Kind: "campaign_recap_bundle",
            Label: "Session recap",
            Summary: "Recap-safe output remains attached to campaign continuity.",
            CreatorPublicationId: "pub-duplicate");
        CreatorPublicationProjection older = new(
            PublicationId: "pub-duplicate",
            Title: "Session recap older projection",
            Kind: "campaign_recap_bundle",
            Summary: "Older publication row.",
            CampaignId: "campaign-a",
            DossierId: null,
            ArtifactId: "artifact-old",
            ProvenanceSummary: "Older provenance",
            DiscoverySummary: "Older discovery",
            Visibility: "group",
            PublicationStatus: "review",
            TrustBand: "bounded",
            Discoverable: false,
            UpdatedAtUtc: DateTimeOffset.Parse("2026-04-03T00:00:00Z"));
        CreatorPublicationProjection newer = older with
        {
            ArtifactId = "artifact-new",
            PublicationStatus = "published",
            TrustBand = "verified",
            Discoverable = true,
            UpdatedAtUtc = DateTimeOffset.Parse("2026-04-03T00:10:00Z")
        };
        CampaignWorkspaceProjection workspace = seed with
        {
            RecapShelf = [recap]
        };

        IReadOnlyList<CampaignWorkspaceProjection> updated = InvokeCampaignSpineAttachCreatorPublicationPosture([workspace], [older, newer]);

        CampaignWorkspaceProjection updatedWorkspace = Assert.Single(updated);
        PublicationSafeProjection updatedRecap = Assert.Single(updatedWorkspace.RecapShelf);
        Assert.Equal("pub-duplicate", updatedRecap.CreatorPublicationId);
        Assert.Equal("published", updatedRecap.PublicationState);
        Assert.Equal("verified", updatedRecap.TrustBand);
        Assert.True(updatedRecap.Discoverable);
    }

    [Fact]
    public void CampaignSpineResolveRosterTransferRequestIdentityNormalizesWhitespacePaddedIds()
    {
        string normalized = InvokeCampaignSpineResolveRosterTransferRequestIdentity("  dossier-1  ", "dossier");

        Assert.Equal("dossier-1", normalized);
    }

    [Fact]
    public void CampaignSpineResolveRosterTransferRequestIdentityThrowsForWhitespaceOnlyIds()
    {
        TargetInvocationException ex = Assert.Throws<TargetInvocationException>(
            () => InvokeCampaignSpineResolveRosterTransferRequestIdentity("   ", "dossier"));

        KeyNotFoundException inner = Assert.IsType<KeyNotFoundException>(ex.InnerException);
        Assert.Contains("Unknown dossier", inner.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void CampaignSpineAttachCreatorPublicationPostureUsesLatestPublication_WhenRecapArtifactIdHasWhitespacePadding()
    {
        CampaignWorkspaceProjection seed = BuildWorkspaceWithRosterAndAftermath();
        PublicationSafeProjection recap = new(
            ProjectionId: "recap-publication-artifact-whitespace-1",
            Kind: "campaign_recap_bundle",
            Label: "Session recap",
            Summary: "Recap-safe output remains attached to campaign continuity.",
            ArtifactId: "  artifact-match  ");
        CreatorPublicationProjection older = new(
            PublicationId: "pub-artifact",
            Title: "Session recap older projection",
            Kind: "campaign_recap_bundle",
            Summary: "Older publication row.",
            CampaignId: "campaign-a",
            DossierId: null,
            ArtifactId: "artifact-match",
            ProvenanceSummary: "Older provenance",
            DiscoverySummary: "Older discovery",
            Visibility: "group",
            PublicationStatus: "review",
            TrustBand: "bounded",
            Discoverable: false,
            UpdatedAtUtc: DateTimeOffset.Parse("2026-04-03T00:00:00Z"));
        CreatorPublicationProjection newer = older with
        {
            PublicationStatus = "published",
            TrustBand = "verified",
            Discoverable = true,
            UpdatedAtUtc = DateTimeOffset.Parse("2026-04-03T00:10:00Z")
        };
        CampaignWorkspaceProjection workspace = seed with
        {
            RecapShelf = [recap]
        };

        IReadOnlyList<CampaignWorkspaceProjection> updated = InvokeCampaignSpineAttachCreatorPublicationPosture([workspace], [older, newer]);

        CampaignWorkspaceProjection updatedWorkspace = Assert.Single(updated);
        PublicationSafeProjection updatedRecap = Assert.Single(updatedWorkspace.RecapShelf);
        Assert.Equal("pub-artifact", updatedRecap.CreatorPublicationId);
        Assert.Equal("published", updatedRecap.PublicationState);
        Assert.Equal("verified", updatedRecap.TrustBand);
        Assert.True(updatedRecap.Discoverable);
    }

    [Fact]
    public void CampaignSpineAttachCreatorPublicationPostureNormalizesUnlinkedWhitespacePublicationIds()
    {
        CampaignWorkspaceProjection seed = BuildWorkspaceWithRosterAndAftermath();
        PublicationSafeProjection recap = new(
            ProjectionId: "recap-publication-unlinked-whitespace-1",
            Kind: "campaign_recap_bundle",
            Label: "Session recap",
            Summary: "Recap-safe output remains attached to campaign continuity.",
            CreatorPublicationId: "  pub-unlinked  ");
        CampaignWorkspaceProjection workspace = seed with
        {
            RecapShelf = [recap]
        };
        CreatorPublicationProjection unrelatedPublication = new(
            PublicationId: "pub-other",
            Title: "Unrelated publication",
            Kind: "campaign_recap_bundle",
            Summary: "Unrelated publication row.",
            CampaignId: "campaign-z",
            DossierId: null,
            ArtifactId: "artifact-other",
            ProvenanceSummary: "Unrelated provenance",
            DiscoverySummary: "Unrelated discovery",
            Visibility: "group",
            PublicationStatus: "review",
            TrustBand: "bounded",
            Discoverable: false,
            UpdatedAtUtc: DateTimeOffset.Parse("2026-04-03T00:00:00Z"));

        IReadOnlyList<CampaignWorkspaceProjection> updated = InvokeCampaignSpineAttachCreatorPublicationPosture([workspace], [unrelatedPublication]);

        CampaignWorkspaceProjection updatedWorkspace = Assert.Single(updated);
        PublicationSafeProjection updatedRecap = Assert.Single(updatedWorkspace.RecapShelf);
        Assert.Equal("pub-unlinked", updatedRecap.CreatorPublicationId);
    }

    [Fact]
    public void CampaignSpineAttachCreatorPublicationPostureNormalizesUnlinkedWhitespaceArtifactIdsWhenPublicationListIsPresent()
    {
        CampaignWorkspaceProjection seed = BuildWorkspaceWithRosterAndAftermath();
        PublicationSafeProjection recap = new(
            ProjectionId: "recap-artifact-unlinked-whitespace-1",
            Kind: "campaign_recap_bundle",
            Label: "Session recap",
            Summary: "Recap-safe output remains attached to campaign continuity.",
            ArtifactId: "  artifact-unlinked  ");
        CampaignWorkspaceProjection workspace = seed with
        {
            RecapShelf = [recap]
        };
        CreatorPublicationProjection unrelatedPublication = new(
            PublicationId: "pub-other",
            Title: "Unrelated publication",
            Kind: "campaign_recap_bundle",
            Summary: "Unrelated publication row.",
            CampaignId: "campaign-z",
            DossierId: null,
            ArtifactId: "artifact-other",
            ProvenanceSummary: "Unrelated provenance",
            DiscoverySummary: "Unrelated discovery",
            Visibility: "group",
            PublicationStatus: "review",
            TrustBand: "bounded",
            Discoverable: false,
            UpdatedAtUtc: DateTimeOffset.Parse("2026-04-03T00:00:00Z"));

        IReadOnlyList<CampaignWorkspaceProjection> updated = InvokeCampaignSpineAttachCreatorPublicationPosture([workspace], [unrelatedPublication]);

        CampaignWorkspaceProjection updatedWorkspace = Assert.Single(updated);
        PublicationSafeProjection updatedRecap = Assert.Single(updatedWorkspace.RecapShelf);
        Assert.Equal("artifact-unlinked", updatedRecap.ArtifactId);
    }

    [Fact]
    public void CampaignSpineAttachCreatorPublicationPostureNormalizesRecapIdsWhenCreatorPublicationsAreEmpty()
    {
        CampaignWorkspaceProjection seed = BuildWorkspaceWithRosterAndAftermath();
        PublicationSafeProjection recap = new(
            ProjectionId: "recap-no-publications-whitespace-1",
            Kind: "campaign_recap_bundle",
            Label: "Session recap",
            Summary: "Recap-safe output remains attached to campaign continuity.",
            ArtifactId: "  artifact-unlinked  ",
            CreatorPublicationId: "  pub-unlinked  ");
        CampaignWorkspaceProjection workspace = seed with
        {
            RecapShelf = [recap]
        };

        IReadOnlyList<CampaignWorkspaceProjection> updated = InvokeCampaignSpineAttachCreatorPublicationPosture(
            [workspace],
            Array.Empty<CreatorPublicationProjection>());

        CampaignWorkspaceProjection updatedWorkspace = Assert.Single(updated);
        PublicationSafeProjection updatedRecap = Assert.Single(updatedWorkspace.RecapShelf);
        Assert.Equal("pub-unlinked", updatedRecap.CreatorPublicationId);
        Assert.Equal("artifact-unlinked", updatedRecap.ArtifactId);
    }

    [Fact]
    public void CampaignSpineBuildCreatorPublicationsDeduplicatesRows_WhenPublicationIdsRepeat()
    {
        CampaignWorkspaceProjection seed = BuildWorkspaceWithRosterAndAftermath();
        PublicationSafeProjection recapA = new(
            ProjectionId: "recap-publication-dedupe-a",
            Kind: "campaign_recap_bundle",
            Label: "Session recap A",
            Summary: "Recap row A",
            CreatorPublicationId: "pub-duplicate");
        PublicationSafeProjection recapB = recapA with
        {
            ProjectionId = "recap-publication-dedupe-b",
            Label = "Session recap B",
            Summary = "Recap row B"
        };
        CampaignWorkspaceProjection workspace = seed with
        {
            RecapShelf = [recapA, recapB]
        };

        IReadOnlyList<CreatorPublicationProjection> publications = InvokeCampaignSpineBuildCreatorPublications([workspace]);

        CreatorPublicationProjection publication = Assert.Single(publications);
        Assert.Equal("pub-duplicate", publication.PublicationId);
    }

    [Fact]
    public void CampaignSpineBuildCreatorPublicationsDeduplicatesRows_WhenPublicationIdsHaveWhitespacePadding()
    {
        CampaignWorkspaceProjection seed = BuildWorkspaceWithRosterAndAftermath();
        PublicationSafeProjection recapA = new(
            ProjectionId: "recap-publication-dedupe-whitespace-a",
            Kind: "campaign_recap_bundle",
            Label: "Session recap A",
            Summary: "Recap row A",
            CreatorPublicationId: "  pub-duplicate  ");
        PublicationSafeProjection recapB = recapA with
        {
            ProjectionId = "recap-publication-dedupe-whitespace-b",
            CreatorPublicationId = "pub-duplicate",
            Label = "Session recap B",
            Summary = "Recap row B"
        };
        CampaignWorkspaceProjection workspace = seed with
        {
            RecapShelf = [recapA, recapB]
        };

        IReadOnlyList<CreatorPublicationProjection> publications = InvokeCampaignSpineBuildCreatorPublications([workspace]);

        CreatorPublicationProjection publication = Assert.Single(publications);
        Assert.Equal("pub-duplicate", publication.PublicationId);
    }

    [Fact]
    public void CampaignSpineBuildCreatorPublicationsNormalizesWhitespaceArtifactIds()
    {
        CampaignWorkspaceProjection seed = BuildWorkspaceWithRosterAndAftermath();
        PublicationSafeProjection recap = new(
            ProjectionId: "recap-publication-artifact-whitespace",
            Kind: "campaign_recap_bundle",
            Label: "Session recap",
            Summary: "Recap row",
            ArtifactId: "  artifact-whitespace  ",
            CreatorPublicationId: "pub-duplicate");
        CampaignWorkspaceProjection workspace = seed with
        {
            RecapShelf = [recap]
        };

        CreatorPublicationProjection publication = Assert.Single(
            InvokeCampaignSpineBuildCreatorPublications([workspace]));

        Assert.Equal("artifact-whitespace", publication.ArtifactId);
    }

    [Fact]
    public void CampaignSpineEnrichWorkspaceRecapShelfUsesCanonicalProjectionIdForFallbackPublicationId()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithRosterAndAftermath();
        CampaignProjection campaign = BuildCampaignProjection(workspace);
        PublicationSafeProjection recapWithWhitespaceProjection = new(
            ProjectionId: "  recap-projection-canonical  ",
            Kind: "campaign_recap_bundle",
            Label: "Session recap",
            Summary: "Recap summary",
            CreatorPublicationId: null);
        PublicationSafeProjection recapWithCanonicalProjection = recapWithWhitespaceProjection with
        {
            ProjectionId = "recap-projection-canonical"
        };

        IReadOnlyList<PublicationSafeProjection> whitespaceResult = InvokeCampaignSpineEnrichWorkspaceRecapShelf(
            campaign,
            workspace.WorkspaceId,
            [recapWithWhitespaceProjection]);
        IReadOnlyList<PublicationSafeProjection> canonicalResult = InvokeCampaignSpineEnrichWorkspaceRecapShelf(
            campaign,
            workspace.WorkspaceId,
            [recapWithCanonicalProjection]);

        PublicationSafeProjection whitespaceRecap = Assert.Single(whitespaceResult);
        PublicationSafeProjection canonicalRecap = Assert.Single(canonicalResult);
        Assert.Equal(canonicalRecap.CreatorPublicationId, whitespaceRecap.CreatorPublicationId);
        Assert.NotNull(whitespaceRecap.CreatorPublicationId);
    }

    [Fact]
    public void CampaignSpineEnrichWorkspaceRecapShelfNormalizesProvidedWhitespacePublicationId()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithRosterAndAftermath();
        CampaignProjection campaign = BuildCampaignProjection(workspace);
        PublicationSafeProjection recap = new(
            ProjectionId: "recap-provided-publication-id-whitespace",
            Kind: "campaign_recap_bundle",
            Label: "Session recap",
            Summary: "Recap summary",
            CreatorPublicationId: "  pub-provided  ");

        PublicationSafeProjection enrichedRecap = Assert.Single(
            InvokeCampaignSpineEnrichWorkspaceRecapShelf(
                campaign,
                workspace.WorkspaceId,
                [recap]));

        Assert.Equal("pub-provided", enrichedRecap.CreatorPublicationId);
    }

    [Fact]
    public void CampaignSpineBuildCreatorPublicationsUsesCanonicalProjectionIdForFallbackArtifactId()
    {
        CampaignWorkspaceProjection seed = BuildWorkspaceWithRosterAndAftermath();
        PublicationSafeProjection recapWithWhitespaceProjection = new(
            ProjectionId: "  recap-artifact-canonical  ",
            Kind: "campaign_recap_bundle",
            Label: "Session recap",
            Summary: "Recap summary",
            CreatorPublicationId: "pub-canonical-artifact");
        PublicationSafeProjection recapWithCanonicalProjection = recapWithWhitespaceProjection with
        {
            ProjectionId = "recap-artifact-canonical"
        };
        CampaignWorkspaceProjection whitespaceWorkspace = seed with
        {
            RecapShelf = [recapWithWhitespaceProjection]
        };
        CampaignWorkspaceProjection canonicalWorkspace = seed with
        {
            RecapShelf = [recapWithCanonicalProjection]
        };

        CreatorPublicationProjection whitespacePublication = Assert.Single(
            InvokeCampaignSpineBuildCreatorPublications([whitespaceWorkspace]));
        CreatorPublicationProjection canonicalPublication = Assert.Single(
            InvokeCampaignSpineBuildCreatorPublications([canonicalWorkspace]));

        Assert.Equal(canonicalPublication.ArtifactId, whitespacePublication.ArtifactId);
        Assert.StartsWith("artifact-", whitespacePublication.ArtifactId, StringComparison.Ordinal);
    }

    [Fact]
    public void CampaignSpineNextSessionCarryForwardTreatsWhitespacePaddedReplayPackageKindAsReplay()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithRosterAndAftermath();
        CampaignProjection campaign = BuildCampaignProjection(workspace);
        AftermathRecapPackageProjection replayPackage = new(
            PackageId: "package-replay-kind-whitespace",
            WorkspaceId: workspace.WorkspaceId,
            CampaignId: workspace.CampaignId,
            RunId: null,
            RunTitle: null,
            PackageKind: "  replay_timeline  ",
            Title: "Replay timeline",
            Summary: "Replay packet stays attached to continuity.",
            ArtifactId: "artifact-replay-kind-whitespace",
            EvidenceLines: ["Replay evidence line."],
            InitiatedByUserId: "gm-1",
            GeneratedAtUtc: DateTimeOffset.Parse("2026-04-03T00:00:00Z"));

        NextSessionCarryForwardProjection? carryForward = InvokeCampaignSpineBuildNextSessionCarryForward(campaign, [replayPackage]);

        Assert.NotNull(carryForward);
        Assert.Contains("replay-safe carry-forward packet", carryForward!.Summary, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void CampaignSpineCampaignMemoryTreatsWhitespacePaddedDowntimePackageKindAsDowntimeBrief()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithRosterAndAftermath();
        CampaignProjection campaign = BuildCampaignProjection(workspace);
        AftermathRecapPackageProjection downtimePackage = new(
            PackageId: "package-downtime-kind-whitespace",
            WorkspaceId: workspace.WorkspaceId,
            CampaignId: workspace.CampaignId,
            RunId: null,
            RunTitle: null,
            PackageKind: "  downtime_brief  ",
            Title: "Downtime brief",
            Summary: "Downtime obligations remain attached to return lane.",
            ArtifactId: "artifact-downtime-kind-whitespace",
            EvidenceLines: ["Downtime evidence line."],
            InitiatedByUserId: "gm-1",
            GeneratedAtUtc: DateTimeOffset.Parse("2026-04-03T00:00:00Z"));

        CampaignMemoryProjection? memory = InvokeCampaignSpineBuildCampaignMemory(campaign, [downtimePackage]);

        Assert.NotNull(memory);
        Assert.Contains("downtime brief", memory!.Summary, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("aftermath recap", memory.Summary, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void CampaignSpineCampaignMemoryTreatsWhitespacePaddedDuplicatePackageIdsAsOneAnchor()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithRosterAndAftermath();
        CampaignProjection campaign = BuildCampaignProjection(workspace);
        AftermathRecapPackageProjection downtimePackage = new(
            PackageId: "package-shared-whitespace-id",
            WorkspaceId: workspace.WorkspaceId,
            CampaignId: workspace.CampaignId,
            RunId: null,
            RunTitle: null,
            PackageKind: "downtime_brief",
            Title: "Downtime brief",
            Summary: "Downtime obligations remain attached to return lane.",
            ArtifactId: "artifact-downtime-shared-whitespace-id",
            EvidenceLines: ["Downtime evidence line."],
            InitiatedByUserId: "gm-1",
            GeneratedAtUtc: DateTimeOffset.Parse("2026-04-03T00:00:00Z"));
        AftermathRecapPackageProjection aftermathVariant = downtimePackage with
        {
            PackageId = "  package-shared-whitespace-id  ",
            PackageKind = "after_action_report",
            Title = "After-action report",
            Summary = "After-action recap packet remains attached to return lane."
        };

        CampaignMemoryProjection? memory = InvokeCampaignSpineBuildCampaignMemory(campaign, [aftermathVariant, downtimePackage]);

        Assert.NotNull(memory);
        Assert.Contains("downtime brief", memory!.Summary, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("after-action report", memory.Summary, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void CampaignSpineNextSessionCarryForwardPrefersMostRecentAftermathPackage()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithRosterAndAftermath();
        CampaignProjection campaign = BuildCampaignProjection(workspace);
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        AftermathRecapPackageProjection olderAftermath = new(
            PackageId: "package-aftermath-older",
            WorkspaceId: workspace.WorkspaceId,
            CampaignId: workspace.CampaignId,
            RunId: "run-1",
            RunTitle: "Dockyard pressure test",
            PackageKind: "after_action_report",
            Title: "Older after-action report",
            Summary: "Older summary should not drive carry-forward output.",
            ArtifactId: "artifact-aftermath-older",
            EvidenceLines: ["Older aftermath evidence line."],
            InitiatedByUserId: "gm-1",
            GeneratedAtUtc: now.AddMinutes(-30));
        AftermathRecapPackageProjection newerAftermath = olderAftermath with
        {
            PackageId = "package-aftermath-newer",
            Title = "Newer after-action report",
            Summary = "Newer summary should drive carry-forward output.",
            ArtifactId = "artifact-aftermath-newer",
            GeneratedAtUtc = now.AddMinutes(30)
        };

        NextSessionCarryForwardProjection? carryForward = InvokeCampaignSpineBuildNextSessionCarryForward(campaign, [olderAftermath, newerAftermath]);

        Assert.NotNull(carryForward);
        Assert.Contains("Newer after-action report", carryForward!.Summary, StringComparison.Ordinal);
        Assert.DoesNotContain("Older after-action report", carryForward.Summary, StringComparison.Ordinal);
    }

    [Fact]
    public void CampaignSpineCampaignMemoryPrefersMostRecentAftermathAndDowntimePackages()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithRosterAndAftermath();
        CampaignProjection campaign = BuildCampaignProjection(workspace);
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        AftermathRecapPackageProjection olderAftermath = new(
            PackageId: "package-memory-aftermath-older",
            WorkspaceId: workspace.WorkspaceId,
            CampaignId: workspace.CampaignId,
            RunId: "run-1",
            RunTitle: "Dockyard pressure test",
            PackageKind: "after_action_report",
            Title: "Older after-action report",
            Summary: "Older after-action summary.",
            ArtifactId: "artifact-memory-aftermath-older",
            EvidenceLines: ["Older aftermath evidence line."],
            InitiatedByUserId: "gm-1",
            GeneratedAtUtc: now.AddMinutes(-40));
        AftermathRecapPackageProjection newerAftermath = olderAftermath with
        {
            PackageId = "package-memory-aftermath-newer",
            Title = "Newer after-action report",
            Summary = "Newer after-action summary.",
            ArtifactId = "artifact-memory-aftermath-newer",
            GeneratedAtUtc = now.AddMinutes(40)
        };
        AftermathRecapPackageProjection olderDowntime = olderAftermath with
        {
            PackageId = "package-memory-downtime-older",
            PackageKind = "downtime_brief",
            Title = "Older downtime brief",
            Summary = "Older downtime summary.",
            ArtifactId = "artifact-memory-downtime-older",
            GeneratedAtUtc = now.AddMinutes(-20)
        };
        AftermathRecapPackageProjection newerDowntime = olderDowntime with
        {
            PackageId = "package-memory-downtime-newer",
            Title = "Newer downtime brief",
            Summary = "Newer downtime summary.",
            ArtifactId = "artifact-memory-downtime-newer",
            GeneratedAtUtc = now.AddMinutes(20)
        };

        CampaignMemoryProjection? memory = InvokeCampaignSpineBuildCampaignMemory(campaign, [olderAftermath, olderDowntime, newerAftermath, newerDowntime]);

        Assert.NotNull(memory);
        Assert.Contains(memory!.EvidenceLines, line => string.Equals(line, "Newer after-action report: Newer after-action summary.", StringComparison.Ordinal));
        Assert.Contains(memory.EvidenceLines, line => string.Equals(line, "Newer downtime brief: Newer downtime summary.", StringComparison.Ordinal));
        Assert.DoesNotContain(memory.EvidenceLines, line => string.Equals(line, "Older after-action report: Older after-action summary.", StringComparison.Ordinal));
        Assert.DoesNotContain(memory.EvidenceLines, line => string.Equals(line, "Older downtime brief: Older downtime summary.", StringComparison.Ordinal));
    }

    [Fact]
    public void CampaignSpineNextSessionCarryForwardPrefersMostRecentConsequencePrepAndTravelReceipts()
    {
        CampaignProjection campaign = BuildCampaignProjection(BuildWorkspaceWithRosterAndAftermath());
        CampaignWorkspaceProjection eventWorkspace = BuildWorkspaceWithEventControls();
        CampaignWorkspaceProjection opsWorkspace = BuildWorkspaceWithPrepLaunchAndTravelPrefetchReceipts();
        CampaignConsequenceProjection consequenceSeed = Assert.Single(Assert.IsAssignableFrom<IReadOnlyList<CampaignConsequenceProjection>>(eventWorkspace.Consequences));
        GovernedPrepLaunchProjection prepSeed = Assert.Single(Assert.IsAssignableFrom<IReadOnlyList<GovernedPrepLaunchProjection>>(opsWorkspace.PrepLaunches));
        TravelPrefetchReceiptProjection travelSeed = Assert.Single(Assert.IsAssignableFrom<IReadOnlyList<TravelPrefetchReceiptProjection>>(opsWorkspace.TravelPrefetches));
        CampaignConsequenceProjection olderConsequence = consequenceSeed with
        {
            Label = "Older consequence",
            Summary = "Older consequence summary.",
            EvidenceLines = [],
            UpdatedAtUtc = consequenceSeed.UpdatedAtUtc.AddMinutes(-15)
        };
        CampaignConsequenceProjection newerConsequence = olderConsequence with
        {
            Label = "Newer consequence",
            Summary = "Newer consequence summary.",
            UpdatedAtUtc = consequenceSeed.UpdatedAtUtc.AddMinutes(15)
        };
        GovernedPrepLaunchProjection olderPrepLaunch = prepSeed with
        {
            LaunchId = "launch-carry-forward-older",
            PacketTitle = "Older prep packet",
            TargetRunTitle = "Older run",
            TargetSceneTitle = "Older scene",
            LaunchedAtUtc = prepSeed.LaunchedAtUtc.AddMinutes(-10)
        };
        GovernedPrepLaunchProjection newerPrepLaunch = olderPrepLaunch with
        {
            LaunchId = "launch-carry-forward-newer",
            PacketTitle = "Newer prep packet",
            TargetRunTitle = "Newer run",
            TargetSceneTitle = "Newer scene",
            LaunchedAtUtc = prepSeed.LaunchedAtUtc.AddMinutes(10)
        };
        TravelPrefetchReceiptProjection olderTravel = travelSeed with
        {
            ReceiptId = "travel-carry-forward-older",
            DeviceRole = "older_device_role",
            Platform = "android",
            StagedAtUtc = travelSeed.StagedAtUtc.AddMinutes(-5)
        };
        TravelPrefetchReceiptProjection newerTravel = olderTravel with
        {
            ReceiptId = "travel-carry-forward-newer",
            DeviceRole = "newer_device_role",
            Platform = "ios",
            StagedAtUtc = travelSeed.StagedAtUtc.AddMinutes(5)
        };

        NextSessionCarryForwardProjection? carryForward = InvokeCampaignSpineBuildNextSessionCarryForward(
            campaign,
            [olderConsequence, newerConsequence],
            [olderPrepLaunch, newerPrepLaunch],
            [olderTravel, newerTravel],
            []);

        Assert.NotNull(carryForward);
        Assert.Contains(carryForward!.EvidenceLines, line => string.Equals(line, "Newer consequence summary.", StringComparison.Ordinal));
        Assert.Contains(carryForward.EvidenceLines, line => string.Equals(line, "Newer prep packet stays bound to Newer run / Newer scene.", StringComparison.Ordinal));
        Assert.Contains(carryForward.EvidenceLines, line => string.Equals(line, "newer_device_role on ios already has the staged travel packet.", StringComparison.Ordinal));
        Assert.DoesNotContain(carryForward.EvidenceLines, line => string.Equals(line, "Older consequence summary.", StringComparison.Ordinal));
    }

    [Fact]
    public void CampaignSpineNextSessionCarryForwardFallsBackToCampaignNameWhenLeadRunMissing()
    {
        CampaignProjection campaign = BuildCampaignProjection(BuildWorkspaceWithRosterAndAftermath());
        SceneProjection activeScene = new(
            SceneId: "scene-orphaned-run",
            RunId: "run-orphaned",
            Title: "Fallback Scene",
            Revision: "v7",
            Status: "active",
            Summary: "Scene signal arrived before run hydration.",
            UpdatedAtUtc: DateTimeOffset.Parse("2026-04-04T00:00:00Z"));
        ObjectiveProjection leadObjective = new(
            ObjectiveId: "objective-fallback",
            Title: "Fallback Objective",
            Status: "open",
            Pressure: "high",
            Summary: "Objective signal arrived before run hydration.",
            UpdatedAtUtc: DateTimeOffset.Parse("2026-04-04T00:01:00Z"));

        NextSessionCarryForwardProjection? carryForward = InvokeCampaignSpineBuildNextSessionCarryForward(
            campaign,
            [],
            [],
            [],
            [],
            leadRun: null,
            activeScene: activeScene,
            leadObjective: leadObjective);

        Assert.NotNull(carryForward);
        Assert.Contains($"{campaign.Name}", carryForward!.Summary, StringComparison.Ordinal);
        Assert.Contains(carryForward.EvidenceLines, line => line.Contains($"{campaign.Name}", StringComparison.Ordinal));
    }

    [Fact]
    public void CampaignSpineResolveWorkspaceNextSafeActionFallsBackToCampaignNameWhenLeadRunMissing()
    {
        CampaignProjection campaign = BuildCampaignProjection(BuildWorkspaceWithRosterAndAftermath());
        WorkspaceRestoreProjection restore = new(
            RestoreId: "restore-1",
            UserId: "user-1",
            RecentDossiers: [],
            RecentCampaigns: [],
            RecentRuleEnvironments: [],
            RecentArtifacts: [],
            Entitlements: [],
            ClaimedDevices: [],
            ConflictSummaries: [],
            LocalOnlyNotes: [],
            GeneratedAtUtc: DateTimeOffset.Parse("2026-04-04T00:00:00Z"));
        SceneProjection activeScene = new(
            SceneId: "scene-orphaned-run",
            RunId: "run-orphaned",
            Title: "Fallback Scene",
            Revision: "v8",
            Status: "active",
            Summary: "Scene signal arrived before run hydration.",
            UpdatedAtUtc: DateTimeOffset.Parse("2026-04-04T00:00:00Z"));
        ObjectiveProjection leadObjective = new(
            ObjectiveId: "objective-fallback",
            Title: "Fallback Objective",
            Status: "open",
            Pressure: "high",
            Summary: "Objective signal arrived before run hydration.",
            UpdatedAtUtc: DateTimeOffset.Parse("2026-04-04T00:01:00Z"));

        string nextSafeAction = InvokeCampaignSpineResolveWorkspaceNextSafeAction(
            campaign,
            restore,
            [],
            [],
            leadRun: null,
            activeScene: activeScene,
            leadObjective: leadObjective);

        Assert.Contains($"in {campaign.Name}", nextSafeAction, StringComparison.Ordinal);
    }

    [Fact]
    public void CampaignSpineResolveWorkspaceNextSafeActionPrefersAttentionCueOverEarlierReviewCue()
    {
        CampaignProjection campaign = BuildCampaignProjection(BuildWorkspaceWithRosterAndAftermath());
        WorkspaceRestoreProjection restore = new(
            RestoreId: "restore-1",
            UserId: "user-1",
            RecentDossiers: [],
            RecentCampaigns: [],
            RecentRuleEnvironments: [],
            RecentArtifacts: [],
            Entitlements: [],
            ClaimedDevices: [],
            ConflictSummaries: [],
            LocalOnlyNotes: [],
            GeneratedAtUtc: DateTimeOffset.Parse("2026-04-04T00:00:00Z"));
        CampaignReadinessCue reviewCue = new(
            CueId: "cue-review-1",
            Severity: "review",
            Title: "Rule environment review",
            Summary: "Ruleset should be reviewed.");
        CampaignReadinessCue attentionCue = new(
            CueId: "cue-attention-1",
            Severity: "attention",
            Title: "Open objective pressure",
            Summary: "Objective pressure remains high.");

        string nextSafeAction = InvokeCampaignSpineResolveWorkspaceNextSafeAction(
            campaign,
            restore,
            [],
            [reviewCue, attentionCue],
            leadRun: null,
            activeScene: null,
            leadObjective: null);

        Assert.Contains("Open objective pressure", nextSafeAction, StringComparison.Ordinal);
        Assert.DoesNotContain("Rule environment review", nextSafeAction, StringComparison.Ordinal);
    }

    [Fact]
    public void CampaignSpineResolveWorkspaceNextSafeActionPrefersWarningCueOverEarlierReviewCue()
    {
        CampaignProjection campaign = BuildCampaignProjection(BuildWorkspaceWithRosterAndAftermath());
        WorkspaceRestoreProjection restore = new(
            RestoreId: "restore-1",
            UserId: "user-1",
            RecentDossiers: [],
            RecentCampaigns: [],
            RecentRuleEnvironments: [],
            RecentArtifacts: [],
            Entitlements: [],
            ClaimedDevices: [],
            ConflictSummaries: [],
            LocalOnlyNotes: [],
            GeneratedAtUtc: DateTimeOffset.Parse("2026-04-04T00:00:00Z"));
        CampaignReadinessCue reviewCue = new(
            CueId: "cue-review-1",
            Severity: "review",
            Title: "Rule environment review",
            Summary: "Ruleset should be reviewed.");
        CampaignReadinessCue warningCue = new(
            CueId: "cue-warning-1",
            Severity: "warning",
            Title: "Continuity gap detected",
            Summary: "At least one dossier is missing continuity.");

        string nextSafeAction = InvokeCampaignSpineResolveWorkspaceNextSafeAction(
            campaign,
            restore,
            [],
            [reviewCue, warningCue],
            leadRun: null,
            activeScene: null,
            leadObjective: null);

        Assert.Contains("Continuity gap detected", nextSafeAction, StringComparison.Ordinal);
        Assert.DoesNotContain("Rule environment review", nextSafeAction, StringComparison.Ordinal);
    }

    [Fact]
    public void CampaignSpineBuildFirstPlayableSessionPrefersAttentionCueOverEarlierReviewCue()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-04T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        CampaignProjection campaign = new(
            CampaignId: "campaign-a",
            GroupId: "group-a",
            Name: "Neon Cradle",
            Status: "active",
            Visibility: "group",
            Summary: "Campaign continuity remains attached to one governed lane.",
            RuleEnvironment: environment,
            ActiveRunId: "run-1",
            CrewIds: ["crew-1"],
            DossierIds: ["dossier-1"],
            RunIds: ["run-1"],
            LatestContinuity: null,
            CreatedAtUtc: now.AddDays(-3),
            UpdatedAtUtc: now);
        WorkspaceRestoreProjection restore = new(
            RestoreId: "restore-1",
            UserId: "user-1",
            RecentDossiers: [],
            RecentCampaigns: [],
            RecentRuleEnvironments: [],
            RecentArtifacts: [],
            Entitlements: [],
            ClaimedDevices: [],
            ConflictSummaries: [],
            LocalOnlyNotes: [],
            GeneratedAtUtc: DateTimeOffset.Parse("2026-04-04T00:00:00Z"));
        CampaignReadinessCue reviewCue = new(
            CueId: "cue-review-1",
            Severity: "review",
            Title: "Rule environment review",
            Summary: "Ruleset should be reviewed.");
        CampaignReadinessCue attentionCue = new(
            CueId: "cue-attention-1",
            Severity: "attention",
            Title: "Open objective pressure",
            Summary: "Objective pressure remains high.");
        CrewProjection crew = new(
            CrewId: "crew-1",
            Name: "Wardens",
            Visibility: "group",
            GroupId: "group-a",
            CampaignId: "campaign-a",
            Members:
            [
                new CrewAssignmentProjection(
                    UserId: "user-1",
                    DossierId: "dossier-1",
                    Role: "face",
                    Availability: "ready",
                    AddedAtUtc: now.AddDays(-2))
            ],
            CreatedAtUtc: now.AddDays(-2),
            UpdatedAtUtc: now.AddMinutes(-1));
        RunnerDossierProjection dossier = new(
            DossierId: "dossier-1",
            RunnerHandle: "Ghostline",
            DisplayName: "Avery Quinn",
            Status: DossierStatuses.Active,
            OwnerUserId: "user-1",
            CrewId: "crew-1",
            CampaignId: "campaign-a",
            CurrentRunId: "run-1",
            CurrentSceneId: "scene-1",
            RuleEnvironment: environment,
            LatestContinuity: null,
            BuildReceiptIds: [],
            SnapshotIds: [],
            Projections: [],
            CreatedAtUtc: now.AddDays(-2),
            UpdatedAtUtc: now.AddMinutes(-2));
        ObjectiveProjection leadObjective = new(
            ObjectiveId: "objective-1",
            Title: "Secure dockyard manifest",
            Status: "open",
            Pressure: "high",
            Summary: "Objective pressure remains high.",
            UpdatedAtUtc: now.AddMinutes(-3));
        SceneProjection activeScene = new(
            SceneId: "scene-1",
            RunId: "run-1",
            Title: "Dockyard checkpoint",
            Revision: "v3",
            Status: "active",
            Summary: "Scene remains active.",
            UpdatedAtUtc: now.AddMinutes(-2));
        RunProjection leadRun = new(
            RunId: "run-1",
            CampaignId: "campaign-a",
            Title: "Dockyard pressure test",
            Status: "active",
            Summary: "Run remains active.",
            ActiveSceneId: "scene-1",
            Objectives: [leadObjective],
            Scenes: [activeScene],
            LatestContinuity: null,
            CreatedAtUtc: now.AddDays(-1),
            UpdatedAtUtc: now.AddMinutes(-1));

        FirstPlayableSessionProjection? firstPlayable = InvokeCampaignSpineBuildFirstPlayableSession(
            campaign,
            restore,
            [reviewCue, attentionCue],
            [crew],
            [dossier],
            leadRun,
            activeScene,
            leadObjective);

        Assert.NotNull(firstPlayable);
        Assert.Contains("Open objective pressure", firstPlayable!.Summary, StringComparison.Ordinal);
        Assert.DoesNotContain("Rule environment review", firstPlayable.Summary, StringComparison.Ordinal);
    }

    [Fact]
    public void CampaignSpineBuildWorkspaceRulesNavigatorDiffsPrefersAttentionCueOverEarlierReviewCue()
    {
        CampaignReadinessCue reviewCue = new(
            CueId: "cue-review-1",
            Severity: "review",
            Title: "Rule environment review",
            Summary: "Ruleset should be reviewed.");
        CampaignReadinessCue attentionCue = new(
            CueId: "cue-attention-1",
            Severity: "attention",
            Title: "Open objective pressure",
            Summary: "Objective pressure remains high.");
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithRosterAndAftermath() with
        {
            ReadinessCues = [reviewCue, attentionCue]
        };

        IReadOnlyList<dynamic> diffs = InvokeCampaignSpineBuildWorkspaceRulesNavigatorDiffs(workspace);
        dynamic readinessDiff = Assert.Single(
            diffs,
            diff => string.Equals((string)diff.Label, "Campaign readiness", StringComparison.Ordinal));
        string reasonSummary = Assert.IsType<string>(readinessDiff.ReasonSummary);

        Assert.Equal("Objective pressure remains high.", reasonSummary);
        Assert.DoesNotContain("Ruleset should be reviewed", reasonSummary, StringComparison.Ordinal);
    }

    [Fact]
    public void CampaignSpineBuildWorkspaceRulesNavigatorDiffsPrefersWarningCueOverEarlierReviewCue()
    {
        CampaignReadinessCue reviewCue = new(
            CueId: "cue-review-1",
            Severity: "review",
            Title: "Rule environment review",
            Summary: "Ruleset should be reviewed.");
        CampaignReadinessCue warningCue = new(
            CueId: "cue-warning-1",
            Severity: "warning",
            Title: "Continuity gap detected",
            Summary: "At least one dossier is missing continuity.");
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithRosterAndAftermath() with
        {
            ReadinessCues = [reviewCue, warningCue]
        };

        IReadOnlyList<dynamic> diffs = InvokeCampaignSpineBuildWorkspaceRulesNavigatorDiffs(workspace);
        dynamic readinessDiff = Assert.Single(
            diffs,
            diff => string.Equals((string)diff.Label, "Campaign readiness", StringComparison.Ordinal));
        string reasonSummary = Assert.IsType<string>(readinessDiff.ReasonSummary);

        Assert.Equal("At least one dossier is missing continuity.", reasonSummary);
        Assert.DoesNotContain("Ruleset should be reviewed", reasonSummary, StringComparison.Ordinal);
    }

    [Fact]
    public void CampaignSpineCampaignMemoryPrefersMostRecentConsequenceRosterPrepAndTravelReceipts()
    {
        CampaignWorkspaceProjection rosterWorkspace = BuildWorkspaceWithRosterAndAftermath();
        CampaignWorkspaceProjection opsWorkspace = BuildWorkspaceWithPrepLaunchAndTravelPrefetchReceipts();
        CampaignWorkspaceProjection eventWorkspace = BuildWorkspaceWithEventControls();
        CampaignProjection campaign = BuildCampaignProjection(rosterWorkspace);
        CampaignConsequenceProjection consequenceSeed = Assert.Single(Assert.IsAssignableFrom<IReadOnlyList<CampaignConsequenceProjection>>(eventWorkspace.Consequences));
        RosterTransferProjection transferSeed = Assert.Single(Assert.IsAssignableFrom<IReadOnlyList<RosterTransferProjection>>(rosterWorkspace.RosterTransfers));
        GovernedPrepLaunchProjection prepSeed = Assert.Single(Assert.IsAssignableFrom<IReadOnlyList<GovernedPrepLaunchProjection>>(opsWorkspace.PrepLaunches));
        TravelPrefetchReceiptProjection travelSeed = Assert.Single(Assert.IsAssignableFrom<IReadOnlyList<TravelPrefetchReceiptProjection>>(opsWorkspace.TravelPrefetches));
        CampaignConsequenceProjection olderConsequence = consequenceSeed with
        {
            Label = "Older consequence",
            Summary = "Older consequence summary.",
            UpdatedAtUtc = consequenceSeed.UpdatedAtUtc.AddMinutes(-12)
        };
        CampaignConsequenceProjection newerConsequence = olderConsequence with
        {
            Label = "Newer consequence",
            Summary = "Newer consequence summary.",
            UpdatedAtUtc = consequenceSeed.UpdatedAtUtc.AddMinutes(12)
        };
        RosterTransferProjection olderTransfer = transferSeed with
        {
            TransferId = "transfer-memory-older",
            Summary = "Older roster transfer summary.",
            TransferredAtUtc = transferSeed.TransferredAtUtc.AddMinutes(-9)
        };
        RosterTransferProjection newerTransfer = olderTransfer with
        {
            TransferId = "transfer-memory-newer",
            Summary = "Newer roster transfer summary.",
            TransferredAtUtc = transferSeed.TransferredAtUtc.AddMinutes(9)
        };
        GovernedPrepLaunchProjection olderPrepLaunch = prepSeed with
        {
            LaunchId = "launch-memory-older",
            Summary = "Older prep launch summary.",
            LaunchedAtUtc = prepSeed.LaunchedAtUtc.AddMinutes(-6)
        };
        GovernedPrepLaunchProjection newerPrepLaunch = olderPrepLaunch with
        {
            LaunchId = "launch-memory-newer",
            Summary = "Newer prep launch summary.",
            LaunchedAtUtc = prepSeed.LaunchedAtUtc.AddMinutes(6)
        };
        TravelPrefetchReceiptProjection olderTravel = travelSeed with
        {
            ReceiptId = "travel-memory-older",
            PrefetchSummary = "Older travel prefetch summary.",
            StagedAtUtc = travelSeed.StagedAtUtc.AddMinutes(-3)
        };
        TravelPrefetchReceiptProjection newerTravel = olderTravel with
        {
            ReceiptId = "travel-memory-newer",
            PrefetchSummary = "Newer travel prefetch summary.",
            StagedAtUtc = travelSeed.StagedAtUtc.AddMinutes(3)
        };

        CampaignMemoryProjection? memory = InvokeCampaignSpineBuildCampaignMemory(
            campaign,
            [olderConsequence, newerConsequence],
            [olderTransfer, newerTransfer],
            [olderPrepLaunch, newerPrepLaunch],
            [olderTravel, newerTravel],
            [],
            null);

        Assert.NotNull(memory);
        Assert.Contains(memory!.EvidenceLines, line => string.Equals(line, "Newer consequence: Newer consequence summary.", StringComparison.Ordinal));
        Assert.Contains(memory.EvidenceLines, line => string.Equals(line, "Newer roster transfer summary.", StringComparison.Ordinal));
        Assert.Contains(memory.EvidenceLines, line => string.Equals(line, "Newer prep launch summary.", StringComparison.Ordinal));
        Assert.Contains(memory.EvidenceLines, line => string.Equals(line, "Newer travel prefetch summary.", StringComparison.Ordinal));
        Assert.DoesNotContain(memory.EvidenceLines, line => string.Equals(line, "Older roster transfer summary.", StringComparison.Ordinal));
    }

    [Fact]
    public void CampaignSpineWorkspaceChangePacketsDeduplicateWhitespacePaddedAftermathPackageIds()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithRosterAndAftermath();
        CampaignProjection campaign = BuildCampaignProjection(workspace);
        AftermathRecapPackageProjection replayPackage = new(
            PackageId: "package-shared-whitespace-id",
            WorkspaceId: workspace.WorkspaceId,
            CampaignId: workspace.CampaignId,
            RunId: null,
            RunTitle: null,
            PackageKind: "replay_timeline",
            Title: "Replay timeline",
            Summary: "Replay packet stays attached to continuity.",
            ArtifactId: "artifact-replay-shared-whitespace-id",
            EvidenceLines: ["Replay evidence line."],
            InitiatedByUserId: "gm-1",
            GeneratedAtUtc: DateTimeOffset.Parse("2026-04-03T00:00:00Z"));
        AftermathRecapPackageProjection downtimeVariant = replayPackage with
        {
            PackageId = "  package-shared-whitespace-id  ",
            PackageKind = "downtime_brief",
            Title = "Downtime brief",
            Summary = "Downtime obligations remain attached to return lane."
        };

        IReadOnlyList<WorkspaceChangePacketProjection> packets = InvokeCampaignSpineBuildWorkspaceChangePackets(campaign, [replayPackage, downtimeVariant]);

        WorkspaceChangePacketProjection packet = Assert.Single(packets);
        Assert.Equal("replay_package", packet.Kind);
    }

    [Fact]
    public void CampaignSpineWorkspaceChangePacketsProjectDowntimeAndAfterActionSignalsWhenBothExist()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithRosterAndAftermath();
        CampaignProjection campaign = BuildCampaignProjection(workspace);
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        AftermathRecapPackageProjection replayPackage = new(
            PackageId: "package-replay",
            WorkspaceId: workspace.WorkspaceId,
            CampaignId: workspace.CampaignId,
            RunId: null,
            RunTitle: null,
            PackageKind: "replay_timeline",
            Title: "Replay timeline",
            Summary: "Replay packet stays attached to continuity.",
            ArtifactId: "artifact-replay",
            EvidenceLines: ["Replay evidence line."],
            InitiatedByUserId: "gm-1",
            GeneratedAtUtc: now);
        AftermathRecapPackageProjection downtimePackage = replayPackage with
        {
            PackageId = "package-downtime",
            PackageKind = "downtime_brief",
            Title = "Downtime brief",
            Summary = "Downtime obligations remain attached to return lane."
        };
        AftermathRecapPackageProjection afterActionPackage = replayPackage with
        {
            PackageId = "package-after-action",
            PackageKind = "after_action_report",
            Title = "After-action report",
            Summary = "After-action recap packet remains attached to return lane."
        };

        IReadOnlyList<WorkspaceChangePacketProjection> packets = InvokeCampaignSpineBuildWorkspaceChangePackets(
            campaign,
            [replayPackage, downtimePackage, afterActionPackage]);

        Assert.Equal(3, packets.Count);
        Assert.Contains(packets, item => string.Equals(item.Kind, "replay_package", StringComparison.Ordinal));
        Assert.Equal(2, packets.Count(item => string.Equals(item.Kind, "aftermath_recap", StringComparison.Ordinal)));
        Assert.Contains(packets, item => string.Equals(item.Label, "Downtime brief", StringComparison.Ordinal));
        Assert.Contains(packets, item => string.Equals(item.Label, "After-action report", StringComparison.Ordinal));
    }

    [Fact]
    public void CampaignSpineWorkspaceChangePacketsPreferMostRecentPackagePerAftermathCategory()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithRosterAndAftermath();
        CampaignProjection campaign = BuildCampaignProjection(workspace);
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        AftermathRecapPackageProjection replayOlder = new(
            PackageId: "package-replay-older",
            WorkspaceId: workspace.WorkspaceId,
            CampaignId: workspace.CampaignId,
            RunId: null,
            RunTitle: null,
            PackageKind: "replay_timeline",
            Title: "Replay timeline older",
            Summary: "Older replay packet.",
            ArtifactId: "artifact-replay-older",
            EvidenceLines: ["Replay evidence line."],
            InitiatedByUserId: "gm-1",
            GeneratedAtUtc: now.AddMinutes(-30));
        AftermathRecapPackageProjection replayNewer = replayOlder with
        {
            PackageId = "package-replay-newer",
            Title = "Replay timeline newer",
            Summary = "Newer replay packet.",
            GeneratedAtUtc = now
        };
        AftermathRecapPackageProjection downtimeOlder = replayOlder with
        {
            PackageId = "package-downtime-older",
            PackageKind = "downtime_brief",
            Title = "Downtime brief older",
            Summary = "Older downtime packet.",
            GeneratedAtUtc = now.AddMinutes(-20)
        };
        AftermathRecapPackageProjection downtimeNewer = downtimeOlder with
        {
            PackageId = "package-downtime-newer",
            Title = "Downtime brief newer",
            Summary = "Newer downtime packet.",
            GeneratedAtUtc = now.AddMinutes(-2)
        };
        AftermathRecapPackageProjection afterActionOlder = replayOlder with
        {
            PackageId = "package-after-action-older",
            PackageKind = "after_action_report",
            Title = "After-action report older",
            Summary = "Older after-action packet.",
            GeneratedAtUtc = now.AddMinutes(-10)
        };
        AftermathRecapPackageProjection afterActionNewer = afterActionOlder with
        {
            PackageId = "package-after-action-newer",
            Title = "After-action report newer",
            Summary = "Newer after-action packet.",
            GeneratedAtUtc = now.AddMinutes(-1)
        };

        IReadOnlyList<WorkspaceChangePacketProjection> packets = InvokeCampaignSpineBuildWorkspaceChangePackets(
            campaign,
            [
                afterActionOlder,
                replayOlder,
                downtimeOlder,
                replayNewer,
                afterActionNewer,
                downtimeNewer
            ]);

        Assert.Contains(packets, item => string.Equals(item.Kind, "replay_package", StringComparison.Ordinal)
                                         && string.Equals(item.Summary, "Newer replay packet.", StringComparison.Ordinal)
                                         && item.UpdatedAtUtc == now);
        Assert.Contains(packets, item => string.Equals(item.Label, "Downtime brief", StringComparison.Ordinal)
                                         && string.Equals(item.Summary, "Newer downtime packet.", StringComparison.Ordinal)
                                         && item.UpdatedAtUtc == now.AddMinutes(-2));
        Assert.Contains(packets, item => string.Equals(item.Label, "After-action report", StringComparison.Ordinal)
                                         && string.Equals(item.Summary, "Newer after-action packet.", StringComparison.Ordinal)
                                         && item.UpdatedAtUtc == now.AddMinutes(-1));
        Assert.DoesNotContain(packets, item => string.Equals(item.Summary, "Older replay packet.", StringComparison.Ordinal));
        Assert.DoesNotContain(packets, item => string.Equals(item.Summary, "Older downtime packet.", StringComparison.Ordinal));
        Assert.DoesNotContain(packets, item => string.Equals(item.Summary, "Older after-action packet.", StringComparison.Ordinal));
    }

    [Fact]
    public void CampaignSpineWorkspaceChangePacketsTrimWhitespacePaddedCarryForwardPacketId()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithRosterAndAftermath();
        CampaignProjection campaign = BuildCampaignProjection(workspace);
        NextSessionCarryForwardProjection carryForward = new(
            CarryForwardId: "  carry-forward-whitespace-id  ",
            Label: "Carry-forward label",
            Summary: "Carry-forward summary",
            ReturnSummary: "Carry-forward return summary",
            NextSafeAction: "Carry-forward next safe action",
            EvidenceLines: ["Carry-forward evidence."],
            UpdatedAtUtc: DateTimeOffset.Parse("2026-04-03T00:00:00Z"));

        IReadOnlyList<WorkspaceChangePacketProjection> packets = InvokeCampaignSpineBuildWorkspaceChangePackets(
            campaign,
            [],
            [],
            carryForward);

        WorkspaceChangePacketProjection packet = Assert.Single(packets);
        Assert.Equal("carry-forward-whitespace-id", packet.PacketId);
        Assert.Equal("next_session_carry_forward", packet.Kind);
    }

    [Fact]
    public void CampaignSpineWorkspaceChangePacketsTrimWhitespacePaddedRecapProjectionIdsWhenAftermathIsMissing()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithRosterAndAftermath();
        CampaignProjection campaign = BuildCampaignProjection(workspace);
        PublicationSafeProjection recap = new(
            ProjectionId: "  recap-projection-whitespace-id  ",
            Kind: "campaign_recap_bundle",
            Label: "Recap label",
            Summary: "Recap summary");

        IReadOnlyList<WorkspaceChangePacketProjection> packets = InvokeCampaignSpineBuildWorkspaceChangePackets(
            campaign,
            [recap],
            [],
            null);

        WorkspaceChangePacketProjection packet = Assert.Single(packets);
        Assert.StartsWith("packet-", packet.PacketId, StringComparison.Ordinal);
        Assert.DoesNotContain(" ", packet.PacketId, StringComparison.Ordinal);
        Assert.DoesNotContain("recap-projection-whitespace-id  ", packet.PacketId, StringComparison.Ordinal);
        Assert.Equal("artifact", packet.Kind);
    }

    [Fact]
    public void CampaignSpineWorkspaceChangePacketsNormalizeWhitespacePaddedRosterTransferIdsBeforePacketProjection()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithRosterAndAftermath();
        CampaignProjection campaign = BuildCampaignProjection(workspace);
        IReadOnlyList<RosterTransferProjection> rosterTransfers = Assert.IsAssignableFrom<IReadOnlyList<RosterTransferProjection>>(workspace.RosterTransfers);
        RosterTransferProjection transfer = Assert.Single(rosterTransfers);
        RosterTransferProjection paddedTransfer = transfer with
        {
            TransferId = "  transfer-1  "
        };

        IReadOnlyList<WorkspaceChangePacketProjection> canonicalPackets = InvokeCampaignSpineBuildWorkspaceChangePackets(
            campaign,
            [],
            [],
            null,
            [transfer],
            [],
            []);
        IReadOnlyList<WorkspaceChangePacketProjection> paddedPackets = InvokeCampaignSpineBuildWorkspaceChangePackets(
            campaign,
            [],
            [],
            null,
            [paddedTransfer],
            [],
            []);

        WorkspaceChangePacketProjection canonicalPacket = Assert.Single(canonicalPackets);
        WorkspaceChangePacketProjection paddedPacket = Assert.Single(paddedPackets);
        Assert.Equal("roster_transfer", canonicalPacket.Kind);
        Assert.Equal(canonicalPacket.PacketId, paddedPacket.PacketId);
    }

    [Fact]
    public void CampaignSpineWorkspaceChangePacketsNormalizeWhitespacePaddedPrepLaunchIdsBeforePacketProjection()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithPrepLaunchAndTravelPrefetchReceipts();
        CampaignProjection campaign = BuildCampaignProjection(workspace);
        IReadOnlyList<GovernedPrepLaunchProjection> prepLaunches = Assert.IsAssignableFrom<IReadOnlyList<GovernedPrepLaunchProjection>>(workspace.PrepLaunches);
        GovernedPrepLaunchProjection prepLaunch = Assert.Single(prepLaunches);
        GovernedPrepLaunchProjection paddedPrepLaunch = prepLaunch with
        {
            LaunchId = "  launch-1  "
        };

        IReadOnlyList<WorkspaceChangePacketProjection> canonicalPackets = InvokeCampaignSpineBuildWorkspaceChangePackets(
            campaign,
            [],
            [],
            null,
            [],
            [prepLaunch],
            []);
        IReadOnlyList<WorkspaceChangePacketProjection> paddedPackets = InvokeCampaignSpineBuildWorkspaceChangePackets(
            campaign,
            [],
            [],
            null,
            [],
            [paddedPrepLaunch],
            []);

        WorkspaceChangePacketProjection canonicalPacket = Assert.Single(canonicalPackets);
        WorkspaceChangePacketProjection paddedPacket = Assert.Single(paddedPackets);
        Assert.Equal("prep_launch", canonicalPacket.Kind);
        Assert.Equal(canonicalPacket.PacketId, paddedPacket.PacketId);
    }

    [Fact]
    public void CampaignSpineWorkspaceChangePacketsNormalizeWhitespacePaddedTravelPrefetchReceiptIdsBeforePacketProjection()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithPrepLaunchAndTravelPrefetchReceipts();
        CampaignProjection campaign = BuildCampaignProjection(workspace);
        IReadOnlyList<TravelPrefetchReceiptProjection> travelPrefetches = Assert.IsAssignableFrom<IReadOnlyList<TravelPrefetchReceiptProjection>>(workspace.TravelPrefetches);
        TravelPrefetchReceiptProjection prefetch = Assert.Single(travelPrefetches);
        TravelPrefetchReceiptProjection paddedPrefetch = prefetch with
        {
            ReceiptId = "  prefetch-1  "
        };

        IReadOnlyList<WorkspaceChangePacketProjection> canonicalPackets = InvokeCampaignSpineBuildWorkspaceChangePackets(
            campaign,
            [],
            [],
            null,
            [],
            [],
            [prefetch]);
        IReadOnlyList<WorkspaceChangePacketProjection> paddedPackets = InvokeCampaignSpineBuildWorkspaceChangePackets(
            campaign,
            [],
            [],
            null,
            [],
            [],
            [paddedPrefetch]);

        WorkspaceChangePacketProjection canonicalPacket = Assert.Single(canonicalPackets);
        WorkspaceChangePacketProjection paddedPacket = Assert.Single(paddedPackets);
        Assert.Equal("travel_prefetch", canonicalPacket.Kind);
        Assert.Equal(canonicalPacket.PacketId, paddedPacket.PacketId);
    }

    [Fact]
    public void CampaignSpineWorkspaceChangePacketsPreferMostRecentRosterTransferReceipt()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithRosterAndAftermath();
        CampaignProjection campaign = BuildCampaignProjection(workspace);
        RosterTransferProjection transfer = Assert.Single(Assert.IsAssignableFrom<IReadOnlyList<RosterTransferProjection>>(workspace.RosterTransfers));
        RosterTransferProjection olderTransfer = transfer with
        {
            TransferId = "transfer-oldest",
            Summary = "Older roster transfer summary.",
            TransferredAtUtc = transfer.TransferredAtUtc.AddMinutes(-30)
        };
        RosterTransferProjection newerTransfer = transfer with
        {
            TransferId = "transfer-newest",
            Summary = "Newest roster transfer summary.",
            TransferredAtUtc = transfer.TransferredAtUtc.AddMinutes(30)
        };

        IReadOnlyList<WorkspaceChangePacketProjection> mixedPackets = InvokeCampaignSpineBuildWorkspaceChangePackets(
            campaign,
            [],
            [],
            null,
            [olderTransfer, newerTransfer],
            [],
            []);
        IReadOnlyList<WorkspaceChangePacketProjection> newestOnlyPackets = InvokeCampaignSpineBuildWorkspaceChangePackets(
            campaign,
            [],
            [],
            null,
            [newerTransfer],
            [],
            []);

        WorkspaceChangePacketProjection mixedPacket = Assert.Single(mixedPackets);
        WorkspaceChangePacketProjection newestOnlyPacket = Assert.Single(newestOnlyPackets);
        Assert.Equal("roster_transfer", mixedPacket.Kind);
        Assert.Equal(newestOnlyPacket.PacketId, mixedPacket.PacketId);
        Assert.Equal("Newest roster transfer summary.", mixedPacket.Summary);
    }

    [Fact]
    public void CampaignSpineWorkspaceChangePacketsPreferMostRecentPrepLaunchReceipt()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithPrepLaunchAndTravelPrefetchReceipts();
        CampaignProjection campaign = BuildCampaignProjection(workspace);
        GovernedPrepLaunchProjection prepLaunch = Assert.Single(Assert.IsAssignableFrom<IReadOnlyList<GovernedPrepLaunchProjection>>(workspace.PrepLaunches));
        GovernedPrepLaunchProjection olderLaunch = prepLaunch with
        {
            LaunchId = "launch-oldest",
            Summary = "Older prep launch summary.",
            LaunchedAtUtc = prepLaunch.LaunchedAtUtc.AddMinutes(-45)
        };
        GovernedPrepLaunchProjection newerLaunch = prepLaunch with
        {
            LaunchId = "launch-newest",
            Summary = "Newest prep launch summary.",
            LaunchedAtUtc = prepLaunch.LaunchedAtUtc.AddMinutes(45)
        };

        IReadOnlyList<WorkspaceChangePacketProjection> mixedPackets = InvokeCampaignSpineBuildWorkspaceChangePackets(
            campaign,
            [],
            [],
            null,
            [],
            [olderLaunch, newerLaunch],
            []);
        IReadOnlyList<WorkspaceChangePacketProjection> newestOnlyPackets = InvokeCampaignSpineBuildWorkspaceChangePackets(
            campaign,
            [],
            [],
            null,
            [],
            [newerLaunch],
            []);

        WorkspaceChangePacketProjection mixedPacket = Assert.Single(mixedPackets);
        WorkspaceChangePacketProjection newestOnlyPacket = Assert.Single(newestOnlyPackets);
        Assert.Equal("prep_launch", mixedPacket.Kind);
        Assert.Equal(newestOnlyPacket.PacketId, mixedPacket.PacketId);
        Assert.Equal("Newest prep launch summary.", mixedPacket.Summary);
    }

    [Fact]
    public void CampaignSpineWorkspaceChangePacketsPreferMostRecentTravelPrefetchReceipt()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithPrepLaunchAndTravelPrefetchReceipts();
        CampaignProjection campaign = BuildCampaignProjection(workspace);
        TravelPrefetchReceiptProjection prefetch = Assert.Single(Assert.IsAssignableFrom<IReadOnlyList<TravelPrefetchReceiptProjection>>(workspace.TravelPrefetches));
        TravelPrefetchReceiptProjection olderPrefetch = prefetch with
        {
            ReceiptId = "prefetch-oldest",
            PrefetchSummary = "Older travel prefetch summary.",
            StagedAtUtc = prefetch.StagedAtUtc.AddMinutes(-20)
        };
        TravelPrefetchReceiptProjection newerPrefetch = prefetch with
        {
            ReceiptId = "prefetch-newest",
            PrefetchSummary = "Newest travel prefetch summary.",
            StagedAtUtc = prefetch.StagedAtUtc.AddMinutes(20)
        };

        IReadOnlyList<WorkspaceChangePacketProjection> mixedPackets = InvokeCampaignSpineBuildWorkspaceChangePackets(
            campaign,
            [],
            [],
            null,
            [],
            [],
            [olderPrefetch, newerPrefetch]);
        IReadOnlyList<WorkspaceChangePacketProjection> newestOnlyPackets = InvokeCampaignSpineBuildWorkspaceChangePackets(
            campaign,
            [],
            [],
            null,
            [],
            [],
            [newerPrefetch]);

        WorkspaceChangePacketProjection mixedPacket = Assert.Single(mixedPackets);
        WorkspaceChangePacketProjection newestOnlyPacket = Assert.Single(newestOnlyPackets);
        Assert.Equal("travel_prefetch", mixedPacket.Kind);
        Assert.Equal(newestOnlyPacket.PacketId, mixedPacket.PacketId);
        Assert.Equal("Newest travel prefetch summary.", mixedPacket.Summary);
    }

    [Fact]
    public void CampaignSpineWorkspaceChangePacketsNormalizeWhitespacePaddedSceneIdsBeforePacketProjection()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithRosterAndAftermath();
        CampaignProjection campaign = BuildCampaignProjection(workspace);
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        ObjectiveProjection leadObjective = new(
            ObjectiveId: "objective-1",
            Title: "Lead objective",
            Status: "open",
            Pressure: "medium",
            Summary: "Objective summary",
            UpdatedAtUtc: now.AddMinutes(2));
        RunProjection leadRun = new(
            RunId: "run-1",
            CampaignId: campaign.CampaignId,
            Title: "Dockyard pressure test",
            Status: "active",
            Summary: "Run summary",
            ActiveSceneId: "scene-1",
            Objectives: [leadObjective],
            Scenes: [],
            LatestContinuity: null,
            CreatedAtUtc: now.AddDays(-1),
            UpdatedAtUtc: now.AddMinutes(3));
        SceneProjection canonicalScene = new(
            SceneId: "scene-1",
            RunId: leadRun.RunId,
            Title: "Dockyard checkpoint",
            Revision: "r3",
            Status: "active",
            Summary: "Scene summary",
            UpdatedAtUtc: now.AddMinutes(4));
        SceneProjection paddedScene = canonicalScene with
        {
            SceneId = "  scene-1  "
        };

        IReadOnlyList<WorkspaceChangePacketProjection> canonicalPackets = InvokeCampaignSpineBuildWorkspaceChangePackets(
            campaign,
            [],
            [],
            null,
            [],
            [],
            [],
            leadRun,
            canonicalScene);
        IReadOnlyList<WorkspaceChangePacketProjection> paddedPackets = InvokeCampaignSpineBuildWorkspaceChangePackets(
            campaign,
            [],
            [],
            null,
            [],
            [],
            [],
            leadRun,
            paddedScene);

        WorkspaceChangePacketProjection canonicalPacket = Assert.Single(canonicalPackets);
        WorkspaceChangePacketProjection paddedPacket = Assert.Single(paddedPackets);
        Assert.Equal("scene", canonicalPacket.Kind);
        Assert.Equal(canonicalPacket.PacketId, paddedPacket.PacketId);
    }

    [Fact]
    public void CampaignSpineWorkspaceChangePacketsNormalizeWhitespacePaddedObjectiveIdsBeforePacketProjection()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithRosterAndAftermath();
        CampaignProjection campaign = BuildCampaignProjection(workspace);
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        ObjectiveProjection canonicalObjective = new(
            ObjectiveId: "objective-1",
            Title: "Lead objective",
            Status: "open",
            Pressure: "medium",
            Summary: "Objective summary",
            UpdatedAtUtc: now.AddMinutes(2));
        ObjectiveProjection paddedObjective = canonicalObjective with
        {
            ObjectiveId = "  objective-1  "
        };

        IReadOnlyList<WorkspaceChangePacketProjection> canonicalPackets = InvokeCampaignSpineBuildWorkspaceChangePackets(
            campaign,
            [],
            [],
            null,
            [],
            [],
            [],
            null,
            null,
            canonicalObjective);
        IReadOnlyList<WorkspaceChangePacketProjection> paddedPackets = InvokeCampaignSpineBuildWorkspaceChangePackets(
            campaign,
            [],
            [],
            null,
            [],
            [],
            [],
            null,
            null,
            paddedObjective);

        WorkspaceChangePacketProjection canonicalPacket = Assert.Single(canonicalPackets);
        WorkspaceChangePacketProjection paddedPacket = Assert.Single(paddedPackets);
        Assert.Equal("objective", canonicalPacket.Kind);
        Assert.Equal(canonicalPacket.PacketId, paddedPacket.PacketId);
    }

    [Fact]
    public void CampaignMemoryPacketDoesNotActivateFromCarryForwardWindowSignalsWithoutMemoryContext()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithEventControlCarryForwardWindowOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        Assert.DoesNotContain(packets, item => string.Equals(item.Kind, "campaign_memory_packet", StringComparison.Ordinal));
    }

    [Fact]
    public void ScenePacketIncludesSceneAndObjectiveLabelsWhenSummariesAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithSceneSignalLabelsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();
        RunProjection leadRun = Assert.Single(workspace.Runs);

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore, leadRun);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "scene_packet", StringComparison.Ordinal));
        Assert.False(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("dockyard checkpoint label", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("hostile extraction team label", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void ScenePacketSummaryFallsBackWhenSceneSummariesAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithSceneSignalLabelsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();
        RunProjection leadRun = Assert.Single(workspace.Runs);

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore, leadRun);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "scene_packet", StringComparison.Ordinal));
        Assert.Contains("compiled from the shared campaign return lane", packet.Summary, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void ScenePacketBindingFallsBackWhenRunAndSceneTitlesAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithSparseRunAndSceneTitles();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();
        RunProjection leadRun = Assert.Single(workspace.Runs);

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore, leadRun);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "scene_packet", StringComparison.Ordinal));
        Assert.Contains("Bound to active run / Active scene on sr6-mainline.", packet.BindingSummary, StringComparison.OrdinalIgnoreCase);
        Assert.Equal("Active scene scene packet", packet.Title);
    }

    [Fact]
    public void AftermathPacketFallsBackToChangeSignalsWhenPackagesAreMissing()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithAftermathChangeSignalsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "aftermath_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("aftermath", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains("change signals", packet.Summary, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void AftermathPacketDeduplicatesIdenticalPackageVersions_WhenPayloadRepeatsSameRow()
    {
        CampaignWorkspaceProjection seed = BuildWorkspaceWithAftermathSignalsOnly();
        IReadOnlyList<AftermathRecapPackageProjection> packages =
            Assert.IsAssignableFrom<IReadOnlyList<AftermathRecapPackageProjection>>(seed.AftermathPackages);
        AftermathRecapPackageProjection first = packages[0];
        CampaignWorkspaceProjection workspace = seed with
        {
            AftermathPackages = [first, first]
        };
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "aftermath_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("2 aftermath or downtime signal(s)", packet.Summary, StringComparison.OrdinalIgnoreCase);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("aftermath downtime brief", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void AftermathPacketDeduplicatesSemanticallyIdenticalPackageVersions_WhenArtifactIdsDiffer()
    {
        CampaignWorkspaceProjection seed = BuildWorkspaceWithAftermathSignalsOnly();
        IReadOnlyList<AftermathRecapPackageProjection> packages =
            Assert.IsAssignableFrom<IReadOnlyList<AftermathRecapPackageProjection>>(seed.AftermathPackages);
        AftermathRecapPackageProjection packageA = packages[0] with
        {
            ArtifactId = "artifact-a"
        };
        AftermathRecapPackageProjection packageB = packageA with
        {
            PackageId = "aftermath-semantic-dup",
            ArtifactId = "artifact-b"
        };
        CampaignWorkspaceProjection workspace = seed with
        {
            AftermathPackages = [packageA, packageB]
        };
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "aftermath_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("2 aftermath or downtime signal(s)", packet.Summary, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void AftermathPacketIncludesSignalLabelsWhenSignalSummariesAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithAftermathSignalLabelsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "aftermath_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("downtime label", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void AftermathPacketFallsBackToSignalLabelsWhenSignalKindsAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithAftermathSparseSignalKindsAndLabelsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "aftermath_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("downtime label", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void AftermathPacketIncludesKindFallbackWhenSignalsAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithAftermathSignalKindsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "aftermath_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("downtime_brief", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void AftermathPacketIncludesRecapKindFallbackWhenRecapSignalsAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithAftermathRecapKindsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "aftermath_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("downtime_brief", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void AftermathPacketDeduplicatesIdenticalRecapSignalVersions_WhenPayloadRepeatsSameRow()
    {
        CampaignWorkspaceProjection seed = BuildWorkspaceWithAftermathRecapKindsOnly();
        IReadOnlyList<PublicationSafeProjection> recaps =
            Assert.IsAssignableFrom<IReadOnlyList<PublicationSafeProjection>>(seed.RecapShelf);
        PublicationSafeProjection first = recaps[0];
        CampaignWorkspaceProjection workspace = seed with
        {
            RecapShelf = [first, first]
        };
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "aftermath_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("1 aftermath or downtime signal(s)", packet.Summary, StringComparison.OrdinalIgnoreCase);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("downtime_brief", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void AftermathPacketFallsBackToRecapLabelWhenRecapKindIsSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithAftermathRecapLabelOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "aftermath_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("downtime recap label", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void AftermathPacketKeepsRecapKindFallbackWhenPackageEvidenceIsVerbose()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithAftermathRecapKindsAndVerbosePackage();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "aftermath_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("downtime_brief", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void AftermathPacketKeepsRecapKindFallbackWhenRecapEvidenceIsVerbose()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithAftermathRecapKindsAndVerboseRecapEvidence();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "aftermath_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("downtime_brief", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void PrepLibraryIncludesEventControlPacketWhenCarryForwardAndChangePacketsExist()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithEventControls();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("event", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains("season", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains("control", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains("return", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
    }

    [Fact]
    public void PrepLibraryIncludesCampaignReturnPacketWhenDiaryAndRelationshipSignalsExist()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithCampaignReturnSignals();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "campaign_return_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("diary", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains("journal", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains("sessionlog", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains("contact", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains("contacts", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains("connection", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains("faction", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains("heat", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains("recap", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains("return", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
    }

    [Fact]
    public void CampaignReturnPacketFallsBackToAftermathSignalsWhenDiaryAndRelationshipSignalsAreMissing()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithAftermathSignalsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "campaign_return_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("aftermath", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("aftermath", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void CampaignReturnPacketFallsBackToRelationshipChangeSignalsWhenConsequenceReceiptsAreMissing()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithRelationshipChangeSignalsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "campaign_return_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("return", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("relationship", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("heat", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void CampaignReturnPacketCountsRelationshipSignalsFromChangePackets()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithRelationshipChangeSignalsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "campaign_return_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("1 relationship signal(s)", packet.Summary, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void CampaignReturnPacketCountsRelationshipSignalsFromFavorAndLoyaltyMutations()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithFavorAndLoyaltyRelationshipSignalsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "campaign_return_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("relationship signal(s)", packet.Summary, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("and 0 relationship signal(s)", packet.Summary, StringComparison.OrdinalIgnoreCase);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("favor", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("loyalty", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void CampaignReturnPacketCountsRelationshipSignalsFromConnectionMutations()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithConnectionRelationshipSignalsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "campaign_return_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("relationship signal(s)", packet.Summary, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("and 0 relationship signal(s)", packet.Summary, StringComparison.OrdinalIgnoreCase);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("connection", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void CampaignReturnPacketCountsRelationshipSignalsFromStreetCredAndPublicAwarenessMutations()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithStreetCredAndPublicAwarenessRelationshipSignalsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "campaign_return_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("relationship signal(s)", packet.Summary, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("and 0 relationship signal(s)", packet.Summary, StringComparison.OrdinalIgnoreCase);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("street cred", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("public awareness", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void CampaignReturnPacketCountsRelationshipSignalsFromCompactStreetCredAndPublicAwarenessMutations()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithCompactStreetCredAndPublicAwarenessRelationshipSignalsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "campaign_return_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("relationship signal(s)", packet.Summary, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("and 0 relationship signal(s)", packet.Summary, StringComparison.OrdinalIgnoreCase);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("streetcred", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("publicawareness", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void CampaignReturnPacketFallsBackToReturnSignalVariantsWhenOtherReceiptsAreMissing()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithCampaignReturnVariantSignalsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "campaign_return_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("return", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("return window", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void CampaignReturnPacketFallsBackToDiarySignalVariantsWhenRecapAndConsequencesAreMissing()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithCampaignDiaryVariantSignalsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "campaign_return_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("diary", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("diary", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void CampaignReturnPacketFallsBackToRelationshipConsequenceVariantsWhenCoreKindsAreNotUsed()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithCampaignReturnRelationshipConsequenceVariantsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "campaign_return_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("return", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("heat pressure", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("fixer pressure", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void CampaignReturnPacketFallsBackToRelationshipSignalVariantsWithoutExplicitMutationVerbs()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithCampaignReturnRelationshipSignalVariantsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "campaign_return_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("return", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("heat pressure", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("fixer obligation", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void CampaignReturnPacketIncludesRelationshipConsequenceReceiptEvidenceWhenConsequenceSummariesAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithCampaignReturnRelationshipReceiptEvidenceOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "campaign_return_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("support case", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void CampaignReturnPacketFallsBackToRelationshipConsequenceLabelsWhenConsequenceKindsAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithSparseRelationshipConsequenceKindsAndLabelsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "campaign_return_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("heat pressure consequence label", StringComparison.OrdinalIgnoreCase));
        Assert.DoesNotContain("and 0 relationship signal(s)", packet.Summary, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void CampaignReturnPacketFallsBackToRelationshipConsequenceLabelsWhenFalloutSignalsAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithSparseRelationshipConsequenceFalloutLabelOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "campaign_return_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("contact fallout consequence label", StringComparison.OrdinalIgnoreCase));
        Assert.DoesNotContain("and 0 relationship signal(s)", packet.Summary, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void CampaignReturnPacketDoesNotActivateFromRelationshipMentionsWithoutMutationSignals()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithSparseRelationshipMentionOnlyConsequenceEvidence();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        Assert.DoesNotContain(packets, item => string.Equals(item.Kind, "campaign_return_packet", StringComparison.Ordinal));
    }

    [Fact]
    public void CampaignReturnPacketDoesNotActivateFromRelationshipConsequenceKindWithoutMutationSignals()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithRelationshipConsequenceKindWithoutMutationOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        Assert.DoesNotContain(packets, item => string.Equals(item.Kind, "campaign_return_packet", StringComparison.Ordinal));
    }

    [Fact]
    public void CampaignReturnPacketDoesNotActivateFromBacklogMentionsWithoutRecapIdentity()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithBacklogMentionsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        Assert.DoesNotContain(packets, item => string.Equals(item.Kind, "campaign_return_packet", StringComparison.Ordinal));
    }

    [Fact]
    public void CampaignReturnPacketDoesNotActivateFromAuditLogMentionsWithoutSessionIdentity()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithAuditLogMentionsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        Assert.DoesNotContain(packets, item => string.Equals(item.Kind, "campaign_return_packet", StringComparison.Ordinal));
    }

    [Fact]
    public void CampaignReturnPacketDoesNotActivateFromRecapitalizationMentionsWithoutAftermathIdentity()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithRecapitalizationMentionsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        Assert.DoesNotContain(packets, item => string.Equals(item.Kind, "campaign_return_packet", StringComparison.Ordinal));
    }

    [Fact]
    public void CampaignReturnPacketDoesNotActivateFromAfterActionableMentionsWithoutAfterActionIdentity()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithAfterActionableMentionsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        Assert.DoesNotContain(packets, item => string.Equals(item.Kind, "campaign_return_packet", StringComparison.Ordinal));
    }

    [Fact]
    public void CampaignReturnPacketDoesNotActivateFromDiscontinuityMentionsWithoutContinuityIdentity()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithDiscontinuityMentionsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        Assert.DoesNotContain(packets, item => string.Equals(item.Kind, "campaign_return_packet", StringComparison.Ordinal));
    }

    [Fact]
    public void CampaignReturnPacketDoesNotActivateFromJournalismKeynoteMentionsWithoutDiaryIdentity()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithJournalismKeynoteMentionsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        Assert.DoesNotContain(packets, item => string.Equals(item.Kind, "campaign_return_packet", StringComparison.Ordinal));
    }

    [Fact]
    public void CampaignReturnPacketDoesNotActivateFromJournalEnterpriseMentionsWithoutDiaryMutationIdentity()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithJournalEnterpriseMentionsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        Assert.DoesNotContain(packets, item => string.Equals(item.Kind, "campaign_return_packet", StringComparison.Ordinal));
    }

    [Fact]
    public void CampaignReturnPacketDoesNotActivateFromJournalUpdateableMentionsWithoutDiaryMutationIdentity()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithJournalUpdateableMentionsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        Assert.DoesNotContain(packets, item => string.Equals(item.Kind, "campaign_return_packet", StringComparison.Ordinal));
    }

    [Fact]
    public void CampaignReturnPacketDoesNotActivateFromCampaignerReturnableWindowshadeMentionsWithoutReturnIdentity()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithCampaignerReturnableWindowshadeMentionsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        Assert.DoesNotContain(packets, item => string.Equals(item.Kind, "campaign_return_packet", StringComparison.Ordinal));
    }

    [Fact]
    public void CampaignReturnPacketActivatesFromCampaignReturningSessionLoopMentions()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithCampaignReturningSessionLoopMentionsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "campaign_return_packet", StringComparison.Ordinal));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("campaign returning session loop", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void CampaignReturnPacketIgnoresFactionInterstateMentionsForRelationshipMutationSignals()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithFactionInterstateMentionsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "campaign_return_packet", StringComparison.Ordinal));
        Assert.Contains("0 relationship signal(s)", packet.Summary, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void CampaignReturnPacketIncludesChangePacketLabelsWhenChangeSummariesAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithCampaignReturnSignalLabelsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "campaign_return_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("return window label", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("fixer obligation label", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void CampaignReturnPacketDeduplicatesIdenticalSignalVersions_WhenPayloadRepeatsSameRow()
    {
        CampaignWorkspaceProjection seed = BuildWorkspaceWithCampaignReturnSignalLabelsOnly();
        IReadOnlyList<WorkspaceChangePacketProjection> seedPackets =
            Assert.IsAssignableFrom<IReadOnlyList<WorkspaceChangePacketProjection>>(seed.ChangePackets);
        WorkspaceChangePacketProjection first = seedPackets[0];
        WorkspaceChangePacketProjection second = seedPackets[1];
        CampaignWorkspaceProjection workspace = seed with
        {
            ChangePackets = [first, first, second]
        };
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "campaign_return_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("2 diary/continuity signal(s)", packet.Summary, StringComparison.OrdinalIgnoreCase);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("return window label", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("fixer obligation label", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void CampaignReturnPacketDeduplicatesSemanticallyIdenticalSignalVersions_WhenProjectionIdsDiffer()
    {
        CampaignWorkspaceProjection seed = BuildWorkspaceWithCampaignReturnSignalLabelsOnly();
        IReadOnlyList<WorkspaceChangePacketProjection> seedPackets =
            Assert.IsAssignableFrom<IReadOnlyList<WorkspaceChangePacketProjection>>(seed.ChangePackets);
        WorkspaceChangePacketProjection first = seedPackets[0];
        WorkspaceChangePacketProjection duplicateWithDifferentId = first with
        {
            PacketId = "packet-1-semantic-dup"
        };
        CampaignWorkspaceProjection workspace = seed with
        {
            ChangePackets = [first, duplicateWithDifferentId]
        };
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "campaign_return_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("1 diary/continuity signal(s)", packet.Summary, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void CampaignReturnPacketDeduplicatesIdenticalRelationshipConsequenceVersions_WhenPayloadRepeatsSameRow()
    {
        CampaignWorkspaceProjection seed = BuildWorkspaceWithCampaignReturnRelationshipConsequenceVariantsOnly();
        IReadOnlyList<CampaignConsequenceProjection> consequences =
            Assert.IsAssignableFrom<IReadOnlyList<CampaignConsequenceProjection>>(seed.Consequences);
        CampaignConsequenceProjection first = consequences[0];
        CampaignConsequenceProjection second = consequences[1];
        CampaignWorkspaceProjection workspace = seed with
        {
            Consequences = [first, first, second]
        };
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "campaign_return_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("2 relationship signal(s)", packet.Summary, StringComparison.OrdinalIgnoreCase);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("heat pressure", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("fixer pressure", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void CampaignReturnPacketDeduplicatesSemanticallyIdenticalRelationshipConsequenceVersions_WhenProjectionIdsDiffer()
    {
        CampaignWorkspaceProjection seed = BuildWorkspaceWithCampaignReturnRelationshipConsequenceVariantsOnly();
        IReadOnlyList<CampaignConsequenceProjection> consequences =
            Assert.IsAssignableFrom<IReadOnlyList<CampaignConsequenceProjection>>(seed.Consequences);
        CampaignConsequenceProjection first = consequences[0];
        CampaignConsequenceProjection duplicateWithDifferentId = first with
        {
            ConsequenceId = "consequence-1-semantic-dup"
        };
        CampaignWorkspaceProjection workspace = seed with
        {
            Consequences = [first, duplicateWithDifferentId]
        };
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "campaign_return_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("1 relationship signal(s)", packet.Summary, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void CampaignReturnPacketDeduplicatesIdenticalAftermathPackageVersions_WhenPayloadRepeatsSameRow()
    {
        CampaignWorkspaceProjection seed = BuildWorkspaceWithAftermathSignalsOnly();
        IReadOnlyList<AftermathRecapPackageProjection> packages =
            Assert.IsAssignableFrom<IReadOnlyList<AftermathRecapPackageProjection>>(seed.AftermathPackages);
        AftermathRecapPackageProjection first = packages[0];
        CampaignWorkspaceProjection workspace = seed with
        {
            AftermathPackages = [first, first]
        };
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "campaign_return_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("2 diary/continuity signal(s) and 0 relationship signal(s)", packet.Summary, StringComparison.OrdinalIgnoreCase);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("aftermath downtime brief", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void CampaignReturnPacketDeduplicatesSemanticallyIdenticalAftermathPackageVersions_WhenPackageIdsDiffer()
    {
        CampaignWorkspaceProjection seed = BuildWorkspaceWithAftermathSignalsOnly();
        IReadOnlyList<AftermathRecapPackageProjection> packages =
            Assert.IsAssignableFrom<IReadOnlyList<AftermathRecapPackageProjection>>(seed.AftermathPackages);
        AftermathRecapPackageProjection package = packages[0];
        AftermathRecapPackageProjection duplicateWithDifferentId = package with
        {
            PackageId = "aftermath-semantic-dup"
        };
        CampaignWorkspaceProjection workspace = seed with
        {
            AftermathPackages = [package, duplicateWithDifferentId]
        };
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packetSummary = Assert.Single(packets, item => string.Equals(item.Kind, "campaign_return_packet", StringComparison.Ordinal));
        Assert.True(packetSummary.Reusable);
        Assert.Contains("2 diary/continuity signal(s) and 0 relationship signal(s)", packetSummary.Summary, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void CampaignReturnPacketDeduplicatesSemanticallyIdenticalAftermathPackageVersions_WhenArtifactIdsDiffer()
    {
        CampaignWorkspaceProjection seed = BuildWorkspaceWithAftermathSignalsOnly();
        IReadOnlyList<AftermathRecapPackageProjection> packages =
            Assert.IsAssignableFrom<IReadOnlyList<AftermathRecapPackageProjection>>(seed.AftermathPackages);
        AftermathRecapPackageProjection package = packages[0] with
        {
            ArtifactId = "artifact-a"
        };
        AftermathRecapPackageProjection duplicateWithDifferentArtifactId = package with
        {
            PackageId = "aftermath-semantic-dup",
            ArtifactId = "artifact-b"
        };
        CampaignWorkspaceProjection workspace = seed with
        {
            AftermathPackages = [package, duplicateWithDifferentArtifactId]
        };
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packetSummary = Assert.Single(packets, item => string.Equals(item.Kind, "campaign_return_packet", StringComparison.Ordinal));
        Assert.True(packetSummary.Reusable);
        Assert.Contains("2 diary/continuity signal(s) and 0 relationship signal(s)", packetSummary.Summary, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void CampaignReturnPacketFallsBackToSignalLabelsWhenChangeSignalKindsAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithCampaignReturnSparseSignalKindsAndLabelsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "campaign_return_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("return window label", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("contact pressure label", StringComparison.OrdinalIgnoreCase));
        Assert.Contains("1 relationship signal(s)", packet.Summary, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void CampaignReturnPacketCountsRelationshipSignalsWhenRelationshipTokensAreSplitAcrossFields()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithCampaignReturnSplitRelationshipSignalTokens();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "campaign_return_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("contact lane label", StringComparison.OrdinalIgnoreCase));
        Assert.Contains("relationship signal(s)", packet.Summary, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("and 0 relationship signal(s)", packet.Summary, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void CampaignReturnPacketCountsRelationshipSignalsWhenStructuredMutationContextAndRelationshipTokensAreSplitAcrossFields()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithCampaignReturnStructuredSplitRelationshipSignalTokens();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "campaign_return_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("contact board label", StringComparison.OrdinalIgnoreCase));
        Assert.Contains("relationship signal(s)", packet.Summary, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("and 0 relationship signal(s)", packet.Summary, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void CampaignReturnPacketCountsRelationshipSignalsWhenConsequenceEvidenceStructuredMutationContextAndRelationshipTokensAreSplitAcrossLines()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithCampaignReturnConsequenceEvidenceStructuredSplitRelationshipSignalTokens();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "campaign_return_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("relationship_window", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("contact board label", StringComparison.OrdinalIgnoreCase));
        Assert.Contains("relationship signal(s)", packet.Summary, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("and 0 relationship signal(s)", packet.Summary, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void CampaignReturnPacketDoesNotActivateFromUnrelatedCarryForwardNotesOnly()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithNonEventCarryForwardOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        Assert.DoesNotContain(packets, item => string.Equals(item.Kind, "campaign_return_packet", StringComparison.Ordinal));
    }

    [Fact]
    public void CampaignReturnPacketDoesNotActivateFromContinuityOnlyCarryForwardNotesWithoutDiaryOrReturnSignals()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithContinuityOnlyCarryForwardNotes();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        Assert.DoesNotContain(packets, item => string.Equals(item.Kind, "campaign_return_packet", StringComparison.Ordinal));
    }

    [Fact]
    public void CampaignReturnPacketIncludesCarryForwardLabelWhenCarryForwardSummariesAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithCampaignReturnCarryForwardLabelOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "campaign_return_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("return lane label", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("reopen from governed return lane", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void CampaignReturnPacketActivatesFromCarryForwardEvidenceLinesWhenPrimaryFieldsAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithCampaignReturnCarryForwardEvidenceSignalsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "campaign_return_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("campaign_return_window", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("contact status changed after downtime", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void CampaignReturnPacketCountsRelationshipSignalsFromCarryForwardEvidenceWhenOtherFamiliesAreMissing()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithCampaignReturnCarryForwardEvidenceSignalsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "campaign_return_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("1 relationship signal(s)", packet.Summary, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void CampaignReturnPacketIncludesKindFallbacksWhenLabelsAndSummariesAreMissing()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithCampaignReturnKindsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "campaign_return_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("campaign_return_window", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("heat_pressure_lane", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void CampaignReturnPacketKeepsKindFallbackEvidenceWhenCarryForwardIsVerbose()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithCampaignReturnKindsAndVerboseCarryForward();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "campaign_return_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("campaign_return_window", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("heat_pressure_lane", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void CampaignReturnPacketKeepsRelationshipKindFallbackWhenDiaryEvidenceIsVerbose()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithCampaignReturnKindsAndVerboseDiaryEvidence();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "campaign_return_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("campaign_return_window", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("heat_pressure_lane", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void CampaignReturnPacketIncludesRecapKindFallbackWhenRecapSignalsAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithCampaignReturnRecapKindsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "campaign_return_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("session_recap", StringComparison.OrdinalIgnoreCase));
    }

    [Theory]
    [InlineData("debriefing")]
    [InlineData("de-briefing")]
    [InlineData("out-briefing")]
    [InlineData("post-session")]
    [InlineData("post-run")]
    [InlineData("post-game")]
    [InlineData("postmortem")]
    [InlineData("afteractionreview")]
    [InlineData("retrospective")]
    [InlineData("hotwash")]
    [InlineData("lessonlearned")]
    public void CampaignReturnPacketIncludesRecapKindFallbackWhenRecapUsesContinuityShorthand(string recapKind)
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithCampaignReturnRecapKindOnly(recapKind);
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "campaign_return_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains(recapKind, StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void CampaignReturnPacketDeduplicatesIdenticalDiaryRecapVersions_WhenPayloadRepeatsSameRow()
    {
        CampaignWorkspaceProjection seed = BuildWorkspaceWithCampaignReturnRecapKindsOnly();
        IReadOnlyList<PublicationSafeProjection> recaps =
            Assert.IsAssignableFrom<IReadOnlyList<PublicationSafeProjection>>(seed.RecapShelf);
        PublicationSafeProjection first = recaps[0];
        CampaignWorkspaceProjection workspace = seed with
        {
            RecapShelf = [first, first]
        };
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "campaign_return_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("1 diary/continuity signal(s) and 0 relationship signal(s)", packet.Summary, StringComparison.OrdinalIgnoreCase);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("session_recap", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void CampaignReturnPacketDeduplicatesSemanticallyIdenticalDiaryRecapVersions_WhenProjectionIdsDiffer()
    {
        CampaignWorkspaceProjection seed = BuildWorkspaceWithCampaignReturnRecapKindsOnly();
        IReadOnlyList<PublicationSafeProjection> recaps =
            Assert.IsAssignableFrom<IReadOnlyList<PublicationSafeProjection>>(seed.RecapShelf);
        PublicationSafeProjection recapA = recaps[0];
        PublicationSafeProjection recapB = recapA with
        {
            ProjectionId = $"{recapA.ProjectionId}-semantic-duplicate"
        };
        CampaignWorkspaceProjection workspace = seed with
        {
            RecapShelf = [recapA, recapB]
        };
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "campaign_return_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("1 diary/continuity signal(s) and 0 relationship signal(s)", packet.Summary, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void CampaignReturnPacketDeduplicatesSemanticallyIdenticalDiaryRecapVersions_WhenArtifactAndPublicationIdsDiffer()
    {
        CampaignWorkspaceProjection seed = BuildWorkspaceWithCampaignReturnRecapKindsOnly();
        IReadOnlyList<PublicationSafeProjection> recaps =
            Assert.IsAssignableFrom<IReadOnlyList<PublicationSafeProjection>>(seed.RecapShelf);
        PublicationSafeProjection recapA = recaps[0] with
        {
            ArtifactId = "artifact-a",
            CreatorPublicationId = "publication-a"
        };
        PublicationSafeProjection recapB = recapA with
        {
            ProjectionId = $"{recapA.ProjectionId}-semantic-duplicate",
            ArtifactId = "artifact-b",
            CreatorPublicationId = "publication-b"
        };
        CampaignWorkspaceProjection workspace = seed with
        {
            RecapShelf = [recapA, recapB]
        };
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "campaign_return_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("1 diary/continuity signal(s) and 0 relationship signal(s)", packet.Summary, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void CampaignReturnPacketFallsBackToRecapLabelWhenRecapKindIsSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithCampaignReturnRecapLabelOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "campaign_return_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("session diary recap label", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void PrepLibraryIncludesPrepLaunchPacketWhenGovernedPrepLaunchReceiptsExist()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithPrepLaunchAndTravelPrefetchReceipts();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "prep_launch_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("prep", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains("launch", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains("audit", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
    }

    [Fact]
    public void PrepLibraryIncludesTravelPrefetchPacketWhenPrefetchReceiptsExist()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithPrepLaunchAndTravelPrefetchReceipts();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "travel_prefetch_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("travel", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains("prefetch", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains("device", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
    }

    [Fact]
    public void PrepLaunchPacketDeduplicatesIdenticalLaunchVersions_WhenPayloadRepeatsSameRow()
    {
        CampaignWorkspaceProjection seed = BuildWorkspaceWithPrepLaunchAndTravelPrefetchReceipts();
        IReadOnlyList<GovernedPrepLaunchProjection> launches =
            Assert.IsAssignableFrom<IReadOnlyList<GovernedPrepLaunchProjection>>(seed.PrepLaunches);
        GovernedPrepLaunchProjection launch = Assert.Single(launches);
        CampaignWorkspaceProjection workspace = seed with
        {
            PrepLaunches = [launch, launch],
            TravelPrefetches = []
        };
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "prep_launch_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("1 prep-launch signal(s)", packet.Summary, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void PrepLaunchPacketDeduplicatesSemanticallyIdenticalLaunchVersions_WhenLaunchIdsDiffer()
    {
        CampaignWorkspaceProjection seed = BuildWorkspaceWithPrepLaunchAndTravelPrefetchReceipts();
        IReadOnlyList<GovernedPrepLaunchProjection> launches =
            Assert.IsAssignableFrom<IReadOnlyList<GovernedPrepLaunchProjection>>(seed.PrepLaunches);
        GovernedPrepLaunchProjection launch = Assert.Single(launches);
        GovernedPrepLaunchProjection duplicateWithDifferentId = launch with
        {
            LaunchId = "launch-semantic-dup"
        };
        CampaignWorkspaceProjection workspace = seed with
        {
            PrepLaunches = [launch, duplicateWithDifferentId],
            TravelPrefetches = []
        };
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "prep_launch_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("1 prep-launch signal(s)", packet.Summary, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void PrepLaunchPacketDeduplicatesSemanticallyIdenticalLaunchVersions_WhenPacketIdsDiffer()
    {
        CampaignWorkspaceProjection seed = BuildWorkspaceWithPrepLaunchAndTravelPrefetchReceipts();
        IReadOnlyList<GovernedPrepLaunchProjection> launches =
            Assert.IsAssignableFrom<IReadOnlyList<GovernedPrepLaunchProjection>>(seed.PrepLaunches);
        GovernedPrepLaunchProjection launch = Assert.Single(launches);
        GovernedPrepLaunchProjection duplicateWithDifferentPacketId = launch with
        {
            PacketId = "prep-packet-semantic-dup"
        };
        CampaignWorkspaceProjection workspace = seed with
        {
            PrepLaunches = [launch, duplicateWithDifferentPacketId],
            TravelPrefetches = []
        };
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "prep_launch_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("1 prep-launch signal(s)", packet.Summary, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void TravelPrefetchPacketDeduplicatesIdenticalReceiptVersions_WhenPayloadRepeatsSameRow()
    {
        CampaignWorkspaceProjection seed = BuildWorkspaceWithPrepLaunchAndTravelPrefetchReceipts();
        IReadOnlyList<TravelPrefetchReceiptProjection> prefetches =
            Assert.IsAssignableFrom<IReadOnlyList<TravelPrefetchReceiptProjection>>(seed.TravelPrefetches);
        TravelPrefetchReceiptProjection prefetch = Assert.Single(prefetches);
        CampaignWorkspaceProjection workspace = seed with
        {
            PrepLaunches = [],
            TravelPrefetches = [prefetch, prefetch]
        };
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "travel_prefetch_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("1 travel-prefetch signal(s)", packet.Summary, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void TravelPrefetchPacketDeduplicatesSemanticallyIdenticalReceiptVersions_WhenReceiptIdsDiffer()
    {
        CampaignWorkspaceProjection seed = BuildWorkspaceWithPrepLaunchAndTravelPrefetchReceipts();
        IReadOnlyList<TravelPrefetchReceiptProjection> prefetches =
            Assert.IsAssignableFrom<IReadOnlyList<TravelPrefetchReceiptProjection>>(seed.TravelPrefetches);
        TravelPrefetchReceiptProjection prefetch = Assert.Single(prefetches);
        TravelPrefetchReceiptProjection duplicateWithDifferentId = prefetch with
        {
            ReceiptId = "prefetch-semantic-dup"
        };
        CampaignWorkspaceProjection workspace = seed with
        {
            PrepLaunches = [],
            TravelPrefetches = [prefetch, duplicateWithDifferentId]
        };
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "travel_prefetch_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("1 travel-prefetch signal(s)", packet.Summary, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void PrepLaunchPacketIncludesFallbackEvidenceWhenLaunchReceiptsAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithSparseOpsReceipts();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();
        RunProjection leadRun = Assert.Single(workspace.Runs);

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore, leadRun);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "prep_launch_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("scene_packet for run-1 / scene-1", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void TravelPrefetchPacketIncludesFallbackEvidenceWhenReceiptSummariesAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithSparseOpsReceipts();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "travel_prefetch_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("travel_cache on ios (mobile/preview)", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void EventControlPacketIncludesOpsFallbackEvidenceWhenReceiptSummariesAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithSparseOpsReceipts();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();
        RunProjection leadRun = Assert.Single(workspace.Runs);

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore, leadRun);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("scene_packet for run-1 / scene-1", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("travel_cache on ios (mobile/preview)", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void TravelPrefetchPacketFallsBackToChangeSignalsWhenReceiptsAreMissing()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithTravelPrefetchChangeSignalsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "travel_prefetch_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("travel", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains("prefetch", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains("change packets", packet.Summary, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void TravelPrefetchPacketIncludesSignalLabelsWhenSignalSummariesAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithTravelPrefetchSignalLabelsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "travel_prefetch_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("travel prefetch label", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void TravelPrefetchPacketFallsBackToSignalLabelsWhenSignalKindsAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithTravelPrefetchSparseSignalKindsAndLabelsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "travel_prefetch_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("travel prefetch label", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void TravelPrefetchPacketFallsBackToSplitSignalTokensWhenSignalKindsAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithTravelPrefetchSparseSignalKindsAndSplitTokens();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "travel_prefetch_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("travel staging label", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void TravelPrefetchPacketIncludesKindFallbackWhenSignalsAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithTravelPrefetchKindsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "travel_prefetch_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("travel_prefetch", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void TravelPrefetchPacketKeepsKindFallbackWhenReceiptEvidenceIsVerbose()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithTravelPrefetchKindsAndVerboseReceiptEvidence();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "travel_prefetch_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("travel_prefetch", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void TravelPrefetchPacketActivatesFromCarryForwardSplitTokensWhenReceiptsLag()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithTravelPrefetchCarryForwardSplitTokensOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "travel_prefetch_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("travel lane note", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("prefetch sealed offline kit", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void TravelPacketIncludesFallbackEvidenceWhenRestoreSummariesAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithRosterAndAftermath();
        WorkspaceRestoreProjection restore = BuildRestoreWithTravelPacketSparseEvidence();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "travel_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("travel_cache on linux (offline/preview)", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("campaign_recap_bundle", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("campaign_approved", StringComparison.OrdinalIgnoreCase));
        Assert.Contains("recap", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
    }

    [Fact]
    public void TravelReadyDeviceDoesNotActivateFromPrefetchingSummaryWithoutTravelIdentity()
    {
        ClaimedDeviceRestoreProjection device = BuildClaimedDeviceRestore(
            deviceRole: "workstation",
            restoreSummary: "Campaign prefetching notes remain continuity-only.");

        bool travelReady = InvokeIsTravelReadyDevice(device);

        Assert.False(travelReady);
    }

    [Fact]
    public void TravelReadyDeviceActivatesFromTravelPrefetchSummaryTokens()
    {
        ClaimedDeviceRestoreProjection device = BuildClaimedDeviceRestore(
            deviceRole: "workstation",
            restoreSummary: "Travel prefetch receipts remain staged for bounded return.");

        bool travelReady = InvokeIsTravelReadyDevice(device);

        Assert.True(travelReady);
    }

    [Fact]
    public void EventControlPacketIncludesOpsReceiptsWhenPrepLaunchAndTravelPrefetchExist()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithPrepLaunchAndTravelPrefetchReceipts();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("event", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains("operations", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains("event-control receipt", packet.Summary, StringComparison.OrdinalIgnoreCase);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("install-local secrets remain local", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void EventControlPacketFallsBackToSignalFamilyVariants()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithEventControlSignalVariants();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("event", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("prep launch", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("travel prefetch", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("crew handoff", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void EventControlPacketFallsBackToRelationshipChangeSignalsWhenConsequenceReceiptsAreMissing()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithEventControlRelationshipSignalsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("event", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("relationship", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("heat", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void EventControlPacketFallsBackToRelationshipConsequenceVariantsWhenCoreKindsAreNotUsed()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithEventControlRelationshipConsequenceVariantsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("event", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains("2 event-control receipt(s)", packet.Summary, StringComparison.OrdinalIgnoreCase);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("heat pressure", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("faction pressure", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void EventControlPacketFallsBackToRelationshipSignalVariantsWithoutExplicitMutationVerbs()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithEventControlRelationshipSignalVariantsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("event", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("heat pressure", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("fixer obligation", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void EventControlPacketIncludesRelationshipConsequenceReceiptEvidenceWhenConsequenceSummariesAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithEventControlRelationshipReceiptEvidenceOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("support case", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void EventControlPacketIncludesSignalLabelsWhenSignalSummariesAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithEventControlSignalLabelsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("season operation label", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("contact pressure label", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void EventControlPacketDeduplicatesIdenticalSignalVersions_WhenPayloadRepeatsSameRow()
    {
        CampaignWorkspaceProjection seed = BuildWorkspaceWithEventControlSignalLabelsOnly();
        IReadOnlyList<WorkspaceChangePacketProjection> seedPackets =
            Assert.IsAssignableFrom<IReadOnlyList<WorkspaceChangePacketProjection>>(seed.ChangePackets);
        WorkspaceChangePacketProjection first = seedPackets[0];
        WorkspaceChangePacketProjection second = seedPackets[1];
        CampaignWorkspaceProjection workspace = seed with
        {
            ChangePackets = [first, first, second]
        };
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("2 event-control receipt(s)", packet.Summary, StringComparison.OrdinalIgnoreCase);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("season operation label", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("contact pressure label", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void EventControlPacketDeduplicatesSemanticallyIdenticalSignalVersions_WhenProjectionIdsDiffer()
    {
        CampaignWorkspaceProjection seed = BuildWorkspaceWithEventControlSignalLabelsOnly();
        IReadOnlyList<WorkspaceChangePacketProjection> seedPackets =
            Assert.IsAssignableFrom<IReadOnlyList<WorkspaceChangePacketProjection>>(seed.ChangePackets);
        WorkspaceChangePacketProjection first = seedPackets[0];
        WorkspaceChangePacketProjection duplicateWithDifferentId = first with
        {
            PacketId = "packet-1-semantic-dup"
        };
        CampaignWorkspaceProjection workspace = seed with
        {
            ChangePackets = [first, duplicateWithDifferentId]
        };
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("1 event-control receipt(s)", packet.Summary, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void EventControlPacketDeduplicatesIdenticalConsequenceVersions_WhenPayloadRepeatsSameRow()
    {
        CampaignWorkspaceProjection seed = BuildWorkspaceWithEventControlRelationshipConsequenceVariantsOnly();
        IReadOnlyList<CampaignConsequenceProjection> consequences =
            Assert.IsAssignableFrom<IReadOnlyList<CampaignConsequenceProjection>>(seed.Consequences);
        CampaignConsequenceProjection first = consequences[0];
        CampaignConsequenceProjection second = consequences[1];
        CampaignWorkspaceProjection workspace = seed with
        {
            Consequences = [first, first, second]
        };
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("2 event-control receipt(s)", packet.Summary, StringComparison.OrdinalIgnoreCase);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("heat pressure", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("faction pressure", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void EventControlPacketDeduplicatesSemanticallyIdenticalConsequenceVersions_WhenProjectionIdsDiffer()
    {
        CampaignWorkspaceProjection seed = BuildWorkspaceWithEventControlRelationshipConsequenceVariantsOnly();
        IReadOnlyList<CampaignConsequenceProjection> consequences =
            Assert.IsAssignableFrom<IReadOnlyList<CampaignConsequenceProjection>>(seed.Consequences);
        CampaignConsequenceProjection first = consequences[0];
        CampaignConsequenceProjection duplicateWithDifferentId = first with
        {
            ConsequenceId = "consequence-1-semantic-dup"
        };
        CampaignWorkspaceProjection workspace = seed with
        {
            Consequences = [first, duplicateWithDifferentId]
        };
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("1 event-control receipt(s)", packet.Summary, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void EventControlPacketDeduplicatesIdenticalPrepAndTravelReceiptVersions_WhenPayloadRepeatsSameRows()
    {
        CampaignWorkspaceProjection seed = BuildWorkspaceWithPrepLaunchAndTravelPrefetchReceipts();
        IReadOnlyList<GovernedPrepLaunchProjection> launches =
            Assert.IsAssignableFrom<IReadOnlyList<GovernedPrepLaunchProjection>>(seed.PrepLaunches);
        IReadOnlyList<TravelPrefetchReceiptProjection> prefetches =
            Assert.IsAssignableFrom<IReadOnlyList<TravelPrefetchReceiptProjection>>(seed.TravelPrefetches);
        GovernedPrepLaunchProjection launch = Assert.Single(launches);
        TravelPrefetchReceiptProjection prefetch = Assert.Single(prefetches);
        CampaignWorkspaceProjection workspace = seed with
        {
            PrepLaunches = [launch, launch],
            TravelPrefetches = [prefetch, prefetch]
        };
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("2 event-control receipt(s)", packet.Summary, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void EventControlPacketDeduplicatesSemanticallyIdenticalPrepAndTravelReceiptVersions_WhenIdsDiffer()
    {
        CampaignWorkspaceProjection seed = BuildWorkspaceWithPrepLaunchAndTravelPrefetchReceipts();
        IReadOnlyList<GovernedPrepLaunchProjection> launches =
            Assert.IsAssignableFrom<IReadOnlyList<GovernedPrepLaunchProjection>>(seed.PrepLaunches);
        IReadOnlyList<TravelPrefetchReceiptProjection> prefetches =
            Assert.IsAssignableFrom<IReadOnlyList<TravelPrefetchReceiptProjection>>(seed.TravelPrefetches);
        GovernedPrepLaunchProjection launch = Assert.Single(launches);
        TravelPrefetchReceiptProjection prefetch = Assert.Single(prefetches);
        GovernedPrepLaunchProjection launchDuplicateWithDifferentId = launch with
        {
            LaunchId = "launch-semantic-dup"
        };
        TravelPrefetchReceiptProjection prefetchDuplicateWithDifferentId = prefetch with
        {
            ReceiptId = "prefetch-semantic-dup"
        };
        CampaignWorkspaceProjection workspace = seed with
        {
            PrepLaunches = [launch, launchDuplicateWithDifferentId],
            TravelPrefetches = [prefetch, prefetchDuplicateWithDifferentId]
        };
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("2 event-control receipt(s)", packet.Summary, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void EventControlPacketDeduplicatesSemanticallyIdenticalPrepLaunchVersions_WhenPacketIdsDiffer()
    {
        CampaignWorkspaceProjection seed = BuildWorkspaceWithPrepLaunchAndTravelPrefetchReceipts();
        IReadOnlyList<GovernedPrepLaunchProjection> launches =
            Assert.IsAssignableFrom<IReadOnlyList<GovernedPrepLaunchProjection>>(seed.PrepLaunches);
        IReadOnlyList<TravelPrefetchReceiptProjection> prefetches =
            Assert.IsAssignableFrom<IReadOnlyList<TravelPrefetchReceiptProjection>>(seed.TravelPrefetches);
        GovernedPrepLaunchProjection launch = Assert.Single(launches);
        TravelPrefetchReceiptProjection prefetch = Assert.Single(prefetches);
        GovernedPrepLaunchProjection launchDuplicateWithDifferentPacketId = launch with
        {
            PacketId = "prep-packet-semantic-dup"
        };
        CampaignWorkspaceProjection workspace = seed with
        {
            PrepLaunches = [launch, launchDuplicateWithDifferentPacketId],
            TravelPrefetches = [prefetch]
        };
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("2 event-control receipt(s)", packet.Summary, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void EventControlPacketFallsBackToRelationshipConsequenceLabelsWhenFalloutSignalsAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithSparseRelationshipConsequenceFalloutLabelOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("contact fallout consequence label", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void EventControlPacketDoesNotActivateFromRelationshipMentionsWithoutMutationSignals()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithSparseRelationshipMentionOnlyConsequenceEvidence();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        Assert.DoesNotContain(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
    }

    [Fact]
    public void EventControlPacketDoesNotActivateFromRelationshipConsequenceKindWithoutMutationSignals()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithRelationshipConsequenceKindWithoutMutationOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        Assert.DoesNotContain(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
    }

    [Fact]
    public void EventControlPacketFallsBackToSignalLabelsWhenEventSignalKindsAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithEventControlSparseSignalKindsAndLabelsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("season operation label", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("contact pressure label", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void EventControlPacketFallsBackToSplitRelationshipSignalTokensWhenSignalKindsAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithEventControlSplitRelationshipSignalTokens();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("season operation label", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("contact lane label", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void EventControlPacketActivatesFromStructuredMutationContextAndRelationshipTokensSplitAcrossFields()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithEventControlStructuredSplitRelationshipSignalTokens();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("season operation label", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("contact board label", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void EventControlPacketActivatesFromConsequenceEvidenceStructuredMutationContextAndRelationshipTokensSplitAcrossLines()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithEventControlConsequenceEvidenceStructuredSplitRelationshipSignalTokens();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("relationship_window", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("contact board label", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void EventControlPacketActivatesFromRelationshipSplitSignalTokensWhenOtherFamiliesAreMissing()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithEventControlRelationshipOnlySplitSignalTokens();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("contact lane label", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("status changed after downtime", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void EventControlPacketIncludesKindFallbackWhenEventSignalsAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithEventControlSignalKindsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("season_operation_checkpoint", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("event_window_shift", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void EventControlPacketIncludesCarryForwardLabelWhenCarryForwardSummariesAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithEventControlCarryForwardLabelOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("event control label", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("open season controls before next launch", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void EventControlPacketDoesNotActivateFromUnrelatedCarryForwardNotesOnly()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithNonEventCarryForwardOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        Assert.DoesNotContain(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
    }

    [Fact]
    public void EventControlPacketDoesNotActivateFromContinuitySignalsOnly()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithEventControlContinuitySignalsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        Assert.DoesNotContain(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
    }

    [Fact]
    public void EventControlPacketDoesNotActivateFromAftermathSignalsOnly()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithEventControlAftermathSignalsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        Assert.DoesNotContain(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
    }

    [Fact]
    public void RosterMovementPacketDoesNotActivateFromContinuityHandoffSignalsWithoutRosterIdentity()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithEventControlContinuitySignalsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        Assert.DoesNotContain(packets, item => string.Equals(item.Kind, "roster_movement_packet", StringComparison.Ordinal));
    }

    [Fact]
    public void RosterMovementPacketDoesNotActivateFromCrewMentionsWithoutMovementSemantics()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithCrewMentionsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        Assert.DoesNotContain(packets, item => string.Equals(item.Kind, "roster_movement_packet", StringComparison.Ordinal));
    }

    [Fact]
    public void EventControlPacketDoesNotActivateFromCrewMentionsWithoutMovementSemantics()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithCrewMentionsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        Assert.DoesNotContain(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
    }

    [Fact]
    public void RosterMovementPacketDoesNotActivateFromCrewRemoveMentionsWithoutMovementSemantics()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithCrewRemoveMentionsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        Assert.DoesNotContain(packets, item => string.Equals(item.Kind, "roster_movement_packet", StringComparison.Ordinal));
    }

    [Fact]
    public void EventControlPacketDoesNotActivateFromCrewRemoveMentionsWithoutMovementSemantics()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithCrewRemoveMentionsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        Assert.DoesNotContain(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
    }

    [Fact]
    public void RosterMovementPacketDoesNotActivateFromCrewBenchmarkMentionsWithoutMovementSemantics()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithCrewBenchmarkMentionsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        Assert.DoesNotContain(packets, item => string.Equals(item.Kind, "roster_movement_packet", StringComparison.Ordinal));
    }

    [Fact]
    public void EventControlPacketDoesNotActivateFromCrewBenchmarkMentionsWithoutMovementSemantics()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithCrewBenchmarkMentionsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        Assert.DoesNotContain(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
    }

    [Fact]
    public void RosterMovementPacketDoesNotActivateFromCrewAssignableMentionsWithoutMovementSemantics()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithCrewAssignableMentionsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        Assert.DoesNotContain(packets, item => string.Equals(item.Kind, "roster_movement_packet", StringComparison.Ordinal));
    }

    [Fact]
    public void EventControlPacketDoesNotActivateFromCrewAssignableMentionsWithoutMovementSemantics()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithCrewAssignableMentionsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        Assert.DoesNotContain(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
    }

    [Fact]
    public void RosterMovementPacketDoesNotActivateFromCrewReturnLaneMentionsWithoutRosterIdentity()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithCrewReturnLaneMentionsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        Assert.DoesNotContain(packets, item => string.Equals(item.Kind, "roster_movement_packet", StringComparison.Ordinal));
    }

    [Fact]
    public void EventControlPacketDoesNotActivateFromCrewReturnLaneMentionsWithoutRosterIdentity()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithCrewReturnLaneMentionsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        Assert.DoesNotContain(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
    }

    [Fact]
    public void RosterMovementPacketDoesNotActivateFromRosterReturnableMentionsWithoutReturnMovementIdentity()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithRosterReturnableMentionsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        Assert.DoesNotContain(packets, item => string.Equals(item.Kind, "roster_movement_packet", StringComparison.Ordinal));
    }

    [Fact]
    public void EventControlPacketDoesNotActivateFromRosterReturnableMentionsWithoutReturnMovementIdentity()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithRosterReturnableMentionsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        Assert.DoesNotContain(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
    }

    [Fact]
    public void EventControlPacketDoesNotActivateFromFactionInterstateMentionsWithoutMutationIdentity()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithFactionInterstateMentionsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        Assert.DoesNotContain(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
    }

    [Fact]
    public void AftermathPacketDoesNotActivateFromRecapitalizationMentionsWithoutAftermathIdentity()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithRecapitalizationMentionsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        Assert.DoesNotContain(packets, item => string.Equals(item.Kind, "aftermath_packet", StringComparison.Ordinal));
    }

    [Fact]
    public void AftermathPacketDoesNotActivateFromRecapitalizationKindWithoutAftermathIdentity()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithRecapitalizationKindOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        Assert.DoesNotContain(packets, item => string.Equals(item.Kind, "aftermath_packet", StringComparison.Ordinal));
    }

    [Fact]
    public void AftermathPacketDoesNotActivateFromAfterActionableMentionsWithoutAfterActionIdentity()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithAfterActionableMentionsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        Assert.DoesNotContain(packets, item => string.Equals(item.Kind, "aftermath_packet", StringComparison.Ordinal));
    }

    [Fact]
    public void EventControlPacketDoesNotActivateFromCooperationMentionsWithoutEventSemantics()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithCooperationMentionsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        Assert.DoesNotContain(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
    }

    [Fact]
    public void PrepLaunchPacketDoesNotActivateFromPreparationRelaunchMentionsWithoutPrepLaunchIdentity()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithPreparationRelaunchMentionsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        Assert.DoesNotContain(packets, item => string.Equals(item.Kind, "prep_launch_packet", StringComparison.Ordinal));
    }

    [Fact]
    public void EventControlPacketDoesNotActivateFromPreparationRelaunchMentionsWithoutPrepLaunchIdentity()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithPreparationRelaunchMentionsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        Assert.DoesNotContain(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
    }

    [Fact]
    public void PrepLaunchPacketDoesNotActivateFromPrepLaunchableMentionsWithoutLaunchIdentity()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithPrepLaunchableMentionsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        Assert.DoesNotContain(packets, item => string.Equals(item.Kind, "prep_launch_packet", StringComparison.Ordinal));
    }

    [Fact]
    public void EventControlPacketDoesNotActivateFromPrepLaunchableMentionsWithoutLaunchIdentity()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithPrepLaunchableMentionsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        Assert.DoesNotContain(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
    }

    [Fact]
    public void TravelPrefetchPacketDoesNotActivateFromTraveloguePrefetchingMentionsWithoutTravelPrefetchIdentity()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithTraveloguePrefetchingMentionsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        Assert.DoesNotContain(packets, item => string.Equals(item.Kind, "travel_prefetch_packet", StringComparison.Ordinal));
    }

    [Fact]
    public void EventControlPacketDoesNotActivateFromTraveloguePrefetchingMentionsWithoutTravelPrefetchIdentity()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithTraveloguePrefetchingMentionsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        Assert.DoesNotContain(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
    }

    [Fact]
    public void TravelPrefetchPacketDoesNotActivateFromTravelPrefetchableMentionsWithoutPrefetchIdentity()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithTravelPrefetchableMentionsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        Assert.DoesNotContain(packets, item => string.Equals(item.Kind, "travel_prefetch_packet", StringComparison.Ordinal));
    }

    [Fact]
    public void EventControlPacketDoesNotActivateFromTravelPrefetchableMentionsWithoutPrefetchIdentity()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithTravelPrefetchableMentionsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        Assert.DoesNotContain(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
    }

    [Fact]
    public void TravelPrefetchPacketDoesNotActivateFromCarryForwardTravelPrefetchableMentionsWithoutPrefetchIdentity()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithTravelPrefetchableCarryForwardMentionsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        Assert.DoesNotContain(packets, item => string.Equals(item.Kind, "travel_prefetch_packet", StringComparison.Ordinal));
    }

    [Fact]
    public void EventControlPacketDoesNotActivateFromCarryForwardTravelPrefetchableMentionsWithoutPrefetchIdentity()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithTravelPrefetchableCarryForwardMentionsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        Assert.DoesNotContain(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
    }

    [Fact]
    public void EventControlPacketDoesNotActivateFromContactlessMentionsWithoutRelationshipIdentity()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithContactlessStatusMentionsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        Assert.DoesNotContain(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
    }

    [Fact]
    public void CampaignReturnPacketDoesNotCountContactStatusMentionsAsRelationshipMutationSignals()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithContactStatusMentionsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "campaign_return_packet", StringComparison.Ordinal));
        Assert.Contains("0 relationship signal(s)", packet.Summary, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void EventControlPacketDoesNotActivateFromContactStatusMentionsWithoutMutationIdentity()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithContactStatusMentionsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        Assert.DoesNotContain(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
    }

    [Fact]
    public void CampaignReturnPacketDoesNotCountContactStateMentionsAsRelationshipMutationSignals()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithContactStateMentionsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "campaign_return_packet", StringComparison.Ordinal));
        Assert.Contains("0 relationship signal(s)", packet.Summary, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void EventControlPacketDoesNotActivateFromContactStateMentionsWithoutMutationIdentity()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithContactStateMentionsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        Assert.DoesNotContain(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
    }

    [Fact]
    public void CampaignReturnPacketDoesNotCountContactWindowMentionsAsRelationshipMutationSignals()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithContactWindowMentionsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "campaign_return_packet", StringComparison.Ordinal));
        Assert.Contains("0 relationship signal(s)", packet.Summary, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void EventControlPacketDoesNotActivateFromContactWindowMentionsWithoutMutationIdentity()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithContactWindowMentionsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        Assert.DoesNotContain(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
    }

    [Fact]
    public void CampaignReturnPacketDoesNotCountContactLaneMentionsAsRelationshipMutationSignals()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithContactLaneMentionsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "campaign_return_packet", StringComparison.Ordinal));
        Assert.Contains("0 relationship signal(s)", packet.Summary, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void EventControlPacketDoesNotActivateFromContactLaneMentionsWithoutMutationIdentity()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithContactLaneMentionsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        Assert.DoesNotContain(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
    }

    [Fact]
    public void CampaignReturnPacketDoesNotCountContactCooldownMentionsAsRelationshipMutationSignals()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithContactCooldownMentionsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "campaign_return_packet", StringComparison.Ordinal));
        Assert.Contains("0 relationship signal(s)", packet.Summary, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void EventControlPacketDoesNotActivateFromContactCooldownMentionsWithoutMutationIdentity()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithContactCooldownMentionsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        Assert.DoesNotContain(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
    }

    [Fact]
    public void CampaignReturnPacketDoesNotCountContactCoolingMentionsAsRelationshipMutationSignals()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithContactCoolingMentionsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "campaign_return_packet", StringComparison.Ordinal));
        Assert.Contains("0 relationship signal(s)", packet.Summary, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void EventControlPacketDoesNotActivateFromContactCoolingMentionsWithoutMutationIdentity()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithContactCoolingMentionsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        Assert.DoesNotContain(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
    }

    [Fact]
    public void CampaignReturnPacketDoesNotCountContactDropboxMentionsAsRelationshipMutationSignals()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithContactDropboxMentionsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "campaign_return_packet", StringComparison.Ordinal));
        Assert.Contains("0 relationship signal(s)", packet.Summary, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void EventControlPacketDoesNotActivateFromContactDropboxMentionsWithoutMutationIdentity()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithContactDropboxMentionsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        Assert.DoesNotContain(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
    }

    [Fact]
    public void CampaignReturnPacketDoesNotCountContactEscalatorMentionsAsRelationshipMutationSignals()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithContactEscalatorMentionsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "campaign_return_packet", StringComparison.Ordinal));
        Assert.Contains("0 relationship signal(s)", packet.Summary, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void EventControlPacketDoesNotActivateFromContactEscalatorMentionsWithoutMutationIdentity()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithContactEscalatorMentionsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        Assert.DoesNotContain(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
    }

    [Fact]
    public void CampaignReturnPacketDoesNotCountContactUpdateableMentionsAsRelationshipMutationSignals()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithContactUpdateableMentionsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "campaign_return_packet", StringComparison.Ordinal));
        Assert.Contains("0 relationship signal(s)", packet.Summary, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void EventControlPacketDoesNotActivateFromContactUpdateableMentionsWithoutMutationIdentity()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithContactUpdateableMentionsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        Assert.DoesNotContain(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
    }

    [Fact]
    public void EventControlPacketDoesNotActivateFromNonThreateningMentionsWithoutOppositionIdentity()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithNonThreateningMentionsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        Assert.DoesNotContain(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
    }

    [Fact]
    public void OppositionPacketDoesNotActivateFromNonThreateningMentionsWithoutOppositionIdentity()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithNonThreateningMentionsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        Assert.DoesNotContain(packets, item => string.Equals(item.Kind, "opposition_packet", StringComparison.Ordinal));
    }

    [Fact]
    public void OppositionPacketDoesNotActivateFromBenignRunObjectivesWithoutOppositionSignals()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithBenignRunSignalsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        RunProjection leadRun = Assert.Single(workspace.Runs);
        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore, leadRun);

        Assert.DoesNotContain(packets, item => string.Equals(item.Kind, "opposition_packet", StringComparison.Ordinal));
    }

    [Fact]
    public void OppositionPacketDoesNotActivateFromBenignActiveSceneSummaryWithoutOppositionSignals()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithBenignSceneSummaryOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        RunProjection leadRun = Assert.Single(workspace.Runs);
        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore, leadRun);

        Assert.DoesNotContain(packets, item => string.Equals(item.Kind, "opposition_packet", StringComparison.Ordinal));
    }

    [Fact]
    public void EventControlPacketDoesNotActivateFromCampaignReturnWindowSignalsOnly()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithCampaignReturnVariantSignalsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        Assert.DoesNotContain(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
    }

    [Fact]
    public void EventControlPacketDoesNotActivateFromCarryForwardWindowLanguageOnly()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithEventControlCarryForwardWindowOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        Assert.DoesNotContain(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
    }

    [Fact]
    public void EventControlPacketDoesNotActivateFromCarryForwardRelationshipSignalsWithoutEventContext()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithEventControlCarryForwardRelationshipSignalsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        Assert.DoesNotContain(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
        Assert.Contains(packets, item => string.Equals(item.Kind, "campaign_return_packet", StringComparison.Ordinal));
    }

    [Fact]
    public void EventControlPacketActivatesFromRosterCarryForwardSignalsWhenOtherFamiliesAreMissing()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithRosterEventCarryForwardOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("roster return carry-forward", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("resolve roster assignment", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void EventControlPacketActivatesFromPrepLaunchCarryForwardSplitTokensWhenOtherFamiliesAreMissing()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithPrepLaunchCarryForwardSplitTokensOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("prep lane note", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("launch the queued packet", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void EventControlPacketActivatesFromTravelPrefetchCarryForwardSplitTokensWhenOtherFamiliesAreMissing()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithTravelPrefetchCarryForwardSplitTokensOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("travel lane note", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("prefetch sealed offline kit", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void EventControlPacketActivatesFromCarryForwardEvidenceLinesWhenPrimaryFieldsAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithEventControlCarryForwardEvidenceSignalsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("campaign", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
    }

    [Fact]
    public void RosterMovementPacketActivatesFromCarryForwardEvidenceLinesWhenPrimaryFieldsAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithRosterCarryForwardEvidenceSignalsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "roster_movement_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("campaign", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
    }

    [Fact]
    public void AftermathPacketActivatesFromCarryForwardSignalsWhenOtherFamiliesLag()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithAftermathCarryForwardSignalsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "aftermath_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("aftermath lane carry-forward", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("review aftermath board", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void AftermathPacketActivatesFromOutBriefCarryForwardSplitTokensWhenOtherFamiliesLag()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithAftermathOutBriefCarryForwardSplitTokensOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "aftermath_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("out brief", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("review recap board", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void AftermathPacketActivatesFromPostMortemCarryForwardSplitTokensWhenOtherFamiliesLag()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithAftermathPostMortemCarryForwardSplitTokensOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "aftermath_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("post mortem", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("review recap board", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void AftermathPacketActivatesFromCarryForwardEvidenceLinesWhenPrimaryFieldsAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithAftermathCarryForwardEvidenceSignalsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "aftermath_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("aftermath", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("aftermath downtime brief", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void AftermathPacketActivatesFromHotWashCarryForwardEvidenceSplitTokensWhenPrimaryFieldsAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithAftermathHotWashCarryForwardEvidenceSplitTokensOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "aftermath_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("aftermath", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("hot-wash", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void AftermathPacketActivatesFromPostSessionAndPostRunCarryForwardEvidenceSplitTokensWhenPrimaryFieldsAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithAftermathPostSessionAndPostRunCarryForwardEvidenceSplitTokensOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "aftermath_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("aftermath", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("post-session", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("post run", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void AftermathPacketUpdatedAtIgnoresUnrelatedCarryForwardTimestampWhenCarryForwardIsNotAnAftermathSignal()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithAftermathSignalAndUnrelatedCarryForwardTimestampSkew();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "aftermath_packet", StringComparison.Ordinal));
        Assert.Equal(DateTimeOffset.Parse("2026-04-03T00:01:00Z"), packet.UpdatedAtUtc);
    }

    [Fact]
    public void EventControlPacketUpdatedAtIgnoresUnrelatedCarryForwardTimestampWhenCarryForwardIsNotAnEventSignal()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithEventControlSignalAndUnrelatedCarryForwardTimestampSkew();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
        Assert.Equal(DateTimeOffset.Parse("2026-04-03T00:01:00Z"), packet.UpdatedAtUtc);
    }

    [Fact]
    public void ContinuityPacketUpdatedAtIgnoresUnrelatedCarryForwardTimestampWhenCarryForwardIsNotAContinuitySignal()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithContinuitySignalAndUnrelatedCarryForwardTimestampSkew();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "continuity_packet", StringComparison.Ordinal));
        Assert.Equal(DateTimeOffset.Parse("2026-04-03T00:01:00Z"), packet.UpdatedAtUtc);
    }

    [Fact]
    public void CampaignReturnPacketUpdatedAtIgnoresUnrelatedCarryForwardTimestampWhenCarryForwardIsNotACampaignReturnSignal()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithCampaignReturnSignalAndUnrelatedCarryForwardTimestampSkew();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "campaign_return_packet", StringComparison.Ordinal));
        Assert.Equal(DateTimeOffset.Parse("2026-04-03T00:01:00Z"), packet.UpdatedAtUtc);
    }

    [Fact]
    public void OppositionPacketUpdatedAtIgnoresUnrelatedCarryForwardTimestampWhenCarryForwardIsNotAnOppositionSignal()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithOppositionSignalAndUnrelatedCarryForwardTimestampSkew();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();
        RunProjection leadRun = Assert.Single(workspace.Runs);

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore, leadRun);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "opposition_packet", StringComparison.Ordinal));
        Assert.Equal(DateTimeOffset.Parse("2026-04-03T00:01:00Z"), packet.UpdatedAtUtc);
    }

    [Fact]
    public void RosterMovementPacketUpdatedAtIgnoresUnrelatedCarryForwardTimestampWhenCarryForwardIsNotARosterSignal()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithRosterSignalAndUnrelatedCarryForwardTimestampSkew();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "roster_movement_packet", StringComparison.Ordinal));
        Assert.Equal(DateTimeOffset.Parse("2026-04-03T00:01:00Z"), packet.UpdatedAtUtc);
    }

    [Fact]
    public void RosterMovementPacketSearchTermsIgnoreUnrelatedCarryForwardTextWhenCarryForwardIsNotARosterSignal()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithRosterSignalAndUnrelatedCarryForwardTimestampSkew();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "roster_movement_packet", StringComparison.Ordinal));
        Assert.Contains("roster", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.DoesNotContain("operator", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.DoesNotContain("queue", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.DoesNotContain("publication", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
    }

    [Fact]
    public void EventControlPacketSummaryFallsBackToConsequenceKindsWhenConsequenceLabelsAreMissing()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithEventControlConsequenceKindsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("heat_pressure_lane", packet.Summary, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("faction_status_window", packet.Summary, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void EventControlPacketIncludesConsequenceKindFallbackInEvidenceWhenConsequenceSignalsAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithEventControlConsequenceKindsSparseOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("heat_pressure_lane", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("faction_status_window", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void EventControlPacketFallsBackToRelationshipConsequenceLabelsWhenConsequenceKindsAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithSparseRelationshipConsequenceKindsAndLabelsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("heat pressure consequence label", StringComparison.OrdinalIgnoreCase));
        Assert.Contains("consequence signal(s)", packet.Summary, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void EventControlPacketKeepsKindFallbackEvidenceWhenCarryForwardIsVerbose()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithEventControlKindsAndVerboseCarryForward();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("season_operation_checkpoint", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("heat_pressure_lane", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void EventControlPacketKeepsConsequenceKindFallbackWhenEventEvidenceIsVerbose()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithEventControlKindsAndVerboseEventEvidence();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("heat_pressure_lane", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("season board lane", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void EventControlPacketFallsBackToExplicitEventSignalVariantsWhenOtherFamiliesAreMissing()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithEventControlExplicitEventSignalsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("event", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains("season", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("event window", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("season operation", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void EventControlPacketFallsBackToRunPressureSignalsWhenReceiptsAreMissing()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithEventControlRunPressureSignalsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        RunProjection leadRun = Assert.Single(workspace.Runs);
        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore, leadRun);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("event", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains("season", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("event window", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("event control board", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void EventControlPacketDeduplicatesIdenticalRunPressureObjectiveVersions_WhenPayloadRepeatsSameRow()
    {
        CampaignWorkspaceProjection seed = BuildWorkspaceWithEventControlRunPressureSignalsOnly();
        RunProjection run = Assert.Single(seed.Runs);
        ObjectiveProjection objective = Assert.Single(run.Objectives);
        RunProjection updatedRun = run with
        {
            Objectives = [objective, objective]
        };
        CampaignWorkspaceProjection workspace = seed with
        {
            Runs = [updatedRun]
        };
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore, updatedRun);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("2 event-control receipt(s)", packet.Summary, StringComparison.OrdinalIgnoreCase);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("event window", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void EventControlPacketIncludesRosterTransferReceiptsWhenChangePacketsAreMissing()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithEventControlRosterTransfersOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("roster", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("season operations roster", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void EventControlPacketDeduplicatesSemanticallyIdenticalRosterTransferVersions_WhenTransferIdsDiffer()
    {
        CampaignWorkspaceProjection seed = BuildWorkspaceWithEventControlRosterTransfersOnly();
        IReadOnlyList<RosterTransferProjection> transfers =
            Assert.IsAssignableFrom<IReadOnlyList<RosterTransferProjection>>(seed.RosterTransfers);
        RosterTransferProjection transfer = Assert.Single(transfers);
        RosterTransferProjection duplicateWithDifferentId = transfer with
        {
            TransferId = "transfer-semantic-dup"
        };
        CampaignWorkspaceProjection workspace = seed with
        {
            RosterTransfers = [transfer, duplicateWithDifferentId]
        };
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("1 event-control receipt(s)", packet.Summary, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void EventControlPacketFallsBackToOppositionSignalVariantsWhenEventFamiliesLag()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithEventControlOppositionSignalsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        RunProjection leadRun = Assert.Single(workspace.Runs);
        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore, leadRun);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("opposition", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("opposition command board", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void EventControlPacketActivatesFromOppositionConsequenceSignalsWhenOtherFamiliesLag()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithOppositionConsequenceKindsSparseOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("opposition", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains("threat", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("opposition_window", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("threat_window", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void EventControlPacketIncludesBothRelationshipAndOppositionConsequencesWhenBothArePresent()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithMixedOppositionAndRelationshipConsequences();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("threat_window", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("heat pressure", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void EventControlPacketFallsBackToOppositionConsequenceLabelWhenConsequenceKindIsSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithOppositionConsequenceLabelOnlyAndSparseKind();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("opposition window label", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void OppositionPacketFallsBackToOppositionChangeSignalsWhenConsequencesAndRunPressureAreMissing()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithOppositionChangeSignalsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "opposition_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("opposition", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains("oppositions", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains("encounter", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains("enemy", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains("hostile", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains("adversary", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains("threat", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains("opfor", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains("opforce", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains("packet", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("opposition", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("threat", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void OppositionPacketFallsBackToEncounterEnemyAndOpforSignalsWhenCanonicalOppositionTermsAreMissing()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithEncounterEnemyAndOpforSignalsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "opposition_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("opposition", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains("opfor", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("encounter", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("enemy", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("opfor", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void EventControlPacketFallsBackToEncounterEnemyAndOpforSignalsWhenCanonicalOppositionTermsAreMissing()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithEncounterEnemyAndOpforSignalsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("opposition", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains("opfor", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("encounter", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("enemy", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("opfor", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void OppositionPacketFallsBackToOpForAndOpforceSignalsWhenCanonicalOppositionTermsAreMissing()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithOpForAndOpforceSignalsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "opposition_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("op_for", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("opforce", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void EventControlPacketFallsBackToOpForAndOpforceSignalsWhenCanonicalOppositionTermsAreMissing()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithOpForAndOpforceSignalsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("op_for", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("opforce", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void EventControlPacketFallsBackToCompactEventControlSignalsWhenCanonicalEventTermsAreMissing()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithCompactEventControlSignalsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("eventcontrol", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("seasonops", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void EventControlPacketFallsBackToCompactSeasonOpSignalWhenPluralVariantIsMissing()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithCompactSeasonOpSignalOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("seasonop", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void EventControlPacketFallsBackToCompactEventCtrlSignalWhenEventControlWordIsAbbreviated()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithCompactEventCtrlSignalOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("eventctrl", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void PrepLaunchPacketFallsBackToCompactPrepLaunchSignalsWhenCanonicalTermsAreMissing()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithCompactPrepLaunchAndTravelPrefetchSignalsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "prep_launch_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("preplaunch", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void EventControlPacketFallsBackToCompactPrepLaunchAndTravelPrefetchSignalsWhenCanonicalTermsAreMissing()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithCompactPrepLaunchAndTravelPrefetchSignalsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("preplaunch", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("travelprefetch", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void OppositionPacketActivatesFromCarryForwardOppositionSignalsWhenOtherFamiliesLag()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithOppositionCarryForwardSignalsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "opposition_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.True(packet.SearchTerms.Count >= 3);
        Assert.Contains("opposition", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
    }

    [Fact]
    public void OppositionPacketActivatesFromCarryForwardOppositionEvidenceLinesWhenPrimaryFieldsAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithOppositionCarryForwardEvidenceSignalsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "opposition_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
    }

    [Fact]
    public void OppositionPacketDoesNotActivateFromUnrelatedCarryForwardThreatModelNotesOnly()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithThreatModelCarryForwardOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        Assert.DoesNotContain(packets, item => string.Equals(item.Kind, "opposition_packet", StringComparison.Ordinal));
    }

    [Fact]
    public void EventControlPacketDoesNotActivateFromUnrelatedCarryForwardThreatModelNotesOnly()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithThreatModelCarryForwardOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        Assert.DoesNotContain(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
    }

    [Fact]
    public void OppositionPacketIncludesSignalLabelsWhenSignalSummariesAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithOppositionSignalLabelsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "opposition_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("opposition window label", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("threat lane label", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void OppositionPacketFallsBackToSignalLabelsWhenOppositionSignalKindsAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithOppositionSparseSignalKindsAndLabelsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "opposition_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("opposition window label", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("threat lane label", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void OppositionPacketSummaryFallsBackToKindsWhenSignalLabelsAreMissing()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithOppositionKindsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "opposition_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("opposition_window", packet.Summary, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("threat_window", packet.Summary, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void OppositionPacketIncludesConsequenceKindFallbackInEvidenceWhenConsequenceSignalsAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithOppositionConsequenceKindsSparseOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "opposition_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("opposition_window", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("threat_window", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void OppositionPacketKeepsConsequenceKindFallbackWhenOppositionEvidenceIsVerbose()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithOppositionConsequenceKindsSparseAndVerboseSignals();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "opposition_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("threat_window", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void OppositionPacketExcludesNonOppositionConsequencesFromSummaryAndEvidence()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithMixedOppositionAndRelationshipConsequences();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "opposition_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("threat_window", StringComparison.OrdinalIgnoreCase));
        Assert.DoesNotContain("heat_pressure_lane", packet.Summary, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain(packet.EvidenceLines, line => line.Contains("heat pressure", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void OppositionPacketFallsBackToConsequenceLabelWhenConsequenceKindIsSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithOppositionConsequenceLabelOnlyAndSparseKind();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "opposition_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("opposition window label", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void OppositionPacketFallsBackToRunPressureWhenConsequencesAreMissing()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithRunPressureSignalsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        RunProjection leadRun = Assert.Single(workspace.Runs);
        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore, leadRun);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "opposition_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("opposition", packet.PacketId, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("hostile", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains("high", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains("run pressure", packet.Summary, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void OppositionPacketDeduplicatesIdenticalRunPressureObjectiveVersions_WhenPayloadRepeatsSameRow()
    {
        CampaignWorkspaceProjection seed = BuildWorkspaceWithRunPressureSignalsOnly();
        RunProjection run = Assert.Single(seed.Runs);
        ObjectiveProjection objective = Assert.Single(run.Objectives);
        RunProjection updatedRun = run with
        {
            Objectives = [objective, objective]
        };
        CampaignWorkspaceProjection workspace = seed with
        {
            Runs = [updatedRun]
        };
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore, updatedRun);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "opposition_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("2 governed opposition signal(s)", packet.Summary, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("run pressure", packet.Summary, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void RosterMovementPacketDeduplicatesIdenticalRunPressureObjectiveVersions_WhenPayloadRepeatsSameRow()
    {
        CampaignWorkspaceProjection seed = BuildWorkspaceWithRosterSignalsOnly();
        RunProjection run = Assert.Single(seed.Runs);
        ObjectiveProjection objective = Assert.Single(run.Objectives);
        RunProjection updatedRun = run with
        {
            Objectives = [objective, objective]
        };
        CampaignWorkspaceProjection workspace = seed with
        {
            Runs = [updatedRun]
        };
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore, updatedRun);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "roster_movement_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("3 roster movement signal(s)", packet.Summary, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("roster-change packets", packet.Summary, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void RosterMovementPacketDeduplicatesSemanticallyIdenticalRunPressureObjectiveVersions_WhenProjectionIdsDiffer()
    {
        CampaignWorkspaceProjection seed = BuildWorkspaceWithRosterSignalsOnly();
        RunProjection run = Assert.Single(seed.Runs);
        ObjectiveProjection objective = Assert.Single(run.Objectives);
        ObjectiveProjection duplicateWithDifferentId = objective with
        {
            ObjectiveId = "objective-semantic-dup"
        };
        RunProjection updatedRun = run with
        {
            Objectives = [objective, duplicateWithDifferentId]
        };
        CampaignWorkspaceProjection workspace = seed with
        {
            Runs = [updatedRun]
        };
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore, updatedRun);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "roster_movement_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("3 roster movement signal(s)", packet.Summary, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void RunboardSummaryDeduplicatesIdenticalOpenObjectiveVersions_WhenPayloadRepeatsSameRow()
    {
        CampaignWorkspaceProjection seed = BuildWorkspaceWithRosterSignalsOnly();
        RunProjection run = Assert.Single(seed.Runs);
        ObjectiveProjection objective = Assert.Single(run.Objectives);
        RunProjection updatedRun = run with
        {
            Objectives = [objective, objective]
        };

        RunboardSummary? summary = InvokeBuildRunboardSummary(seed, updatedRun);
        Assert.NotNull(summary);

        Assert.Contains("1 objective(s) still need attention", summary!.ObjectiveSummary, StringComparison.OrdinalIgnoreCase);
        Assert.Single(summary.Blockers);
    }

    [Fact]
    public void PrepLibraryOrderingPrioritizesOppositionAndRosterPacketsAheadOfNewerOpsReceipts()
    {
        CampaignWorkspaceProjection oppositionWorkspace = BuildWorkspaceWithOppositionChangeSignalsOnly();
        CampaignWorkspaceProjection rosterWorkspace = BuildWorkspaceWithRosterAndAftermath();
        CampaignWorkspaceProjection opsWorkspace = BuildWorkspaceWithPrepLaunchAndTravelPrefetchReceipts();
        CampaignWorkspaceProjection workspace = oppositionWorkspace with
        {
            RosterTransfers = rosterWorkspace.RosterTransfers,
            PrepLaunches = opsWorkspace.PrepLaunches,
            TravelPrefetches = opsWorkspace.TravelPrefetches
        };
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        int oppositionIndex = IndexOfPacketKind(packets, "opposition_packet");
        int rosterIndex = IndexOfPacketKind(packets, "roster_movement_packet");
        int prepLaunchIndex = IndexOfPacketKind(packets, "prep_launch_packet");
        int travelPrefetchIndex = IndexOfPacketKind(packets, "travel_prefetch_packet");

        Assert.True(oppositionIndex >= 0);
        Assert.True(rosterIndex >= 0);
        Assert.True(prepLaunchIndex >= 0);
        Assert.True(travelPrefetchIndex >= 0);
        Assert.True(oppositionIndex < prepLaunchIndex);
        Assert.True(oppositionIndex < travelPrefetchIndex);
        Assert.True(rosterIndex < prepLaunchIndex);
        Assert.True(rosterIndex < travelPrefetchIndex);
    }

    [Fact]
    public void PrepLibraryOrderingPrioritizesEventControlPacketAheadOfNewerOpsReceipts()
    {
        CampaignWorkspaceProjection eventWorkspace = BuildWorkspaceWithEventControls();
        CampaignWorkspaceProjection opsWorkspace = BuildWorkspaceWithPrepLaunchAndTravelPrefetchReceipts();
        CampaignWorkspaceProjection workspace = eventWorkspace with
        {
            PrepLaunches = opsWorkspace.PrepLaunches,
            TravelPrefetches = opsWorkspace.TravelPrefetches
        };
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        int eventControlIndex = IndexOfPacketKind(packets, "event_control_packet");
        int prepLaunchIndex = IndexOfPacketKind(packets, "prep_launch_packet");
        int travelPrefetchIndex = IndexOfPacketKind(packets, "travel_prefetch_packet");

        Assert.True(eventControlIndex >= 0);
        Assert.True(prepLaunchIndex >= 0);
        Assert.True(travelPrefetchIndex >= 0);
        Assert.True(eventControlIndex < prepLaunchIndex);
        Assert.True(eventControlIndex < travelPrefetchIndex);
    }

    [Fact]
    public void RosterMovementPacketFallsBackToChangeAndCarryForwardSignalsWhenTransfersAreMissing()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithRosterSignalsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        RunProjection leadRun = Assert.Single(workspace.Runs);
        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore, leadRun);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "roster_movement_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("roster", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains("crew", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains("roster-change packets", packet.Summary, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void RosterMovementPacketIncludesChangeAndCarryForwardLabelsWhenSummariesAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithRosterSignalLabelsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        RunProjection leadRun = Assert.Single(workspace.Runs);
        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore, leadRun);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "roster_movement_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("crew assignment label", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("roster return label", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void RosterMovementPacketFallsBackToSignalLabelsWhenSignalKindsAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithRosterSparseSignalKindsAndLabelsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        RunProjection leadRun = Assert.Single(workspace.Runs);
        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore, leadRun);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "roster_movement_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("crew assignment label", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("roster return label", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void RosterMovementPacketFallsBackToSplitRosterMovementSignalTokensWhenSignalKindsAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithRosterSplitMovementSignalTokens();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        RunProjection leadRun = Assert.Single(workspace.Runs);
        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore, leadRun);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "roster_movement_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("movement board label", StringComparison.OrdinalIgnoreCase));
        Assert.Contains("roster movement signal(s)", packet.Summary, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void RosterMovementPacketFallsBackToCompactRosterMovementSignalsWhenCanonicalRosterTermsAreMissing()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithCompactRosterMovementSignalsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        RunProjection leadRun = Assert.Single(workspace.Runs);
        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore, leadRun);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "roster_movement_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("rostermove", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("crewhandoff", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void RosterMovementPacketIncludesKindFallbackWhenSignalsAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithRosterSignalKindsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        RunProjection leadRun = Assert.Single(workspace.Runs);
        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore, leadRun);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "roster_movement_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("roster_assignment", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void RosterMovementPacketIncludesTransferIdentityFallbackWhenTransferSummariesAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithRosterTransfersSparseOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "roster_movement_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("Ghostline transfer Neon Cradle -> Season Ops", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void EventControlPacketIncludesRosterTransferIdentityFallbackWhenTransferSummariesAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithRosterTransfersSparseOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("Ghostline transfer Neon Cradle -> Season Ops", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void EventControlPacketFallsBackToRosterSignalLabelsWhenSignalKindsAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithRosterSparseSignalKindsAndLabelsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        RunProjection leadRun = Assert.Single(workspace.Runs);
        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore, leadRun);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("crew assignment label", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void EventControlPacketFallsBackToSplitRosterMovementSignalTokensWhenSignalKindsAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithRosterSplitMovementSignalTokens();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        RunProjection leadRun = Assert.Single(workspace.Runs);
        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore, leadRun);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("movement board label", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void RosterMovementPacketActivatesFromRosterConsequenceSignalsWhenOtherFamiliesLag()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithRosterConsequenceKindsSparseOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "roster_movement_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("roster_assignment", StringComparison.OrdinalIgnoreCase));
        Assert.Contains("roster movement signal(s)", packet.Summary, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void EventControlPacketActivatesFromRosterConsequenceSignalsWhenOtherFamiliesLag()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithRosterConsequenceKindsSparseOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("roster_assignment", StringComparison.OrdinalIgnoreCase));
        Assert.Contains("event-control receipt(s)", packet.Summary, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void RosterMovementPacketFallsBackToRosterConsequenceLabelWhenConsequenceKindIsSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithRosterConsequenceLabelOnlyAndSparseKind();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "roster_movement_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("roster movement consequence label", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void EventControlPacketFallsBackToRosterConsequenceLabelWhenConsequenceKindIsSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithRosterConsequenceLabelOnlyAndSparseKind();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("roster movement consequence label", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void RosterMovementPacketKeepsSignalKindFallbackWhenTransferEvidenceIsVerbose()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithRosterTransfersSparseAndVerboseOpsEvidence();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "roster_movement_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("roster_assignment", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("Ghostline transfer Neon Cradle -> Season Ops", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void EventControlPacketKeepsRosterTransferIdentityWhenOpsEvidenceIsVerbose()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithRosterTransfersSparseAndVerboseOpsEvidence();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "event_control_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("Ghostline transfer Neon Cradle -> Season Ops", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void PrepLaunchPacketFallsBackToChangeSignalsWhenLaunchReceiptsAreMissing()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithPrepLaunchChangeSignalsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        RunProjection leadRun = Assert.Single(workspace.Runs);
        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore, leadRun);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "prep_launch_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("prep", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains("launch", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains("change packets", packet.Summary, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void PrepLaunchPacketIncludesSignalLabelsWhenLaunchSummariesAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithPrepLaunchSignalLabelsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        RunProjection leadRun = Assert.Single(workspace.Runs);
        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore, leadRun);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "prep_launch_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("scene prep label", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void PrepLaunchPacketFallsBackToSignalLabelsWhenSignalKindsAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithPrepLaunchSparseSignalKindsAndLabelsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        RunProjection leadRun = Assert.Single(workspace.Runs);
        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore, leadRun);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "prep_launch_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("scene prep launch label", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void PrepLaunchPacketFallsBackToSplitSignalTokensWhenSignalKindsAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithPrepLaunchSparseSignalKindsAndSplitTokens();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        RunProjection leadRun = Assert.Single(workspace.Runs);
        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore, leadRun);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "prep_launch_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("scene prep label", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void PrepLaunchPacketIncludesKindFallbackWhenSignalsAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithPrepLaunchKindsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        RunProjection leadRun = Assert.Single(workspace.Runs);
        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore, leadRun);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "prep_launch_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("prep_launch", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void PrepLaunchPacketKeepsKindFallbackWhenLaunchEvidenceIsVerbose()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithPrepLaunchKindsAndVerboseLaunchEvidence();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        RunProjection leadRun = Assert.Single(workspace.Runs);
        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore, leadRun);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "prep_launch_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("prep_launch", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("season prep lane", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void PrepLaunchPacketActivatesFromCarryForwardSplitTokensWhenReceiptsLag()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithPrepLaunchCarryForwardSplitTokensOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "prep_launch_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("prep lane note", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("launch the queued packet", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void PrepLaunchPacketActivatesFromCarryForwardEvidenceLinesWhenPrimaryFieldsAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithPrepLaunchCarryForwardEvidenceSignalsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "prep_launch_packet", StringComparison.Ordinal));
        Assert.True(packet.Reusable);
        Assert.Contains("launch", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("prep launch remains queued", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void PrepLaunchPacketUpdatedAtIgnoresUnrelatedCarryForwardTimestampWhenCarryForwardIsNotAPrepLaunchSignal()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithPrepLaunchSignalAndUnrelatedCarryForwardTimestampSkew();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "prep_launch_packet", StringComparison.Ordinal));
        Assert.Equal(DateTimeOffset.Parse("2026-04-03T00:01:00Z"), packet.UpdatedAtUtc);
    }

    [Fact]
    public void TravelPrefetchPacketUpdatedAtIgnoresUnrelatedCarryForwardTimestampWhenCarryForwardIsNotATravelPrefetchSignal()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithTravelPrefetchSignalAndUnrelatedCarryForwardTimestampSkew();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "travel_prefetch_packet", StringComparison.Ordinal));
        Assert.Equal(DateTimeOffset.Parse("2026-04-03T00:01:00Z"), packet.UpdatedAtUtc);
    }

    [Fact]
    public void ContinuityPacketFallsBackToCarryForwardAndContinuityChangeSignals()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithContinuitySignalsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "continuity_packet", StringComparison.Ordinal));
        Assert.False(packet.Reusable);
        Assert.Contains("continuity", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains("continuity signal", packet.Summary, StringComparison.OrdinalIgnoreCase);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("carry-forward", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void ContinuityPacketIncludesSignalLabelsWhenSignalSummariesAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithContinuitySignalLabelsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "continuity_packet", StringComparison.Ordinal));
        Assert.False(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("continuity carry-forward label", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("return handoff label", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void ContinuityPacketFallsBackToSignalLabelsWhenSignalKindsAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithContinuitySparseSignalKindsAndLabelsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "continuity_packet", StringComparison.Ordinal));
        Assert.False(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("continuity carry-forward label", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("return handoff label", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void ContinuityPacketDeduplicatesIdenticalSignalVersions_WhenPayloadRepeatsSameRow()
    {
        CampaignWorkspaceProjection seed = BuildWorkspaceWithContinuitySignalLabelsOnly();
        IReadOnlyList<WorkspaceChangePacketProjection> seedPackets =
            Assert.IsAssignableFrom<IReadOnlyList<WorkspaceChangePacketProjection>>(seed.ChangePackets);
        WorkspaceChangePacketProjection first = Assert.Single(seedPackets);
        CampaignWorkspaceProjection workspace = seed with
        {
            ChangePackets = [first, first]
        };
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "continuity_packet", StringComparison.Ordinal));
        Assert.False(packet.Reusable);
        Assert.Contains("2 continuity signal(s)", packet.Summary, StringComparison.OrdinalIgnoreCase);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("continuity carry-forward label", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("return handoff label", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void ContinuityPacketDeduplicatesIdenticalRecapSignalVersions_WhenPayloadRepeatsSameRow()
    {
        CampaignWorkspaceProjection seed = BuildWorkspaceWithContinuityRecapKindsOnly();
        IReadOnlyList<PublicationSafeProjection> recaps =
            Assert.IsAssignableFrom<IReadOnlyList<PublicationSafeProjection>>(seed.RecapShelf);
        PublicationSafeProjection recap = Assert.Single(recaps);
        CampaignWorkspaceProjection workspace = seed with
        {
            RecapShelf = [recap, recap]
        };
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "continuity_packet", StringComparison.Ordinal));
        Assert.False(packet.Reusable);
        Assert.Contains("1 recap-safe output(s)", packet.Summary, StringComparison.OrdinalIgnoreCase);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("session_recap", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void ContinuityPacketIncludesKindFallbackWhenSignalsAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithContinuitySignalKindsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "continuity_packet", StringComparison.Ordinal));
        Assert.False(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("next_session_carry_forward", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void ContinuityPacketIncludesRecapKindFallbackWhenRecapSignalsAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithContinuityRecapKindsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "continuity_packet", StringComparison.Ordinal));
        Assert.False(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("session_recap", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void ContinuityPacketKeepsRecapKindFallbackWhenCarryForwardIsVerbose()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithContinuityRecapKindsAndVerboseCarryForward();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "continuity_packet", StringComparison.Ordinal));
        Assert.False(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("session_recap", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void ContinuityPacketKeepsContinuityKindFallbackWhenRecapEvidenceIsVerbose()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithContinuityKindsAndVerboseRecapEvidence();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "continuity_packet", StringComparison.Ordinal));
        Assert.False(packet.Reusable);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("next_session_carry_forward", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(packet.EvidenceLines, line => line.Contains("Session recap lane", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void ContinuityPacketDoesNotActivateFromDiscontinuityMentionsWithoutContinuityIdentity()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithDiscontinuityMentionsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        Assert.DoesNotContain(packets, item => string.Equals(item.Kind, "continuity_packet", StringComparison.Ordinal));
    }

    [Fact]
    public void ContinuityPacketDoesNotActivateFromUnrelatedCarryForwardNotesOnly()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithUnrelatedContinuityCarryForwardNotesOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        Assert.DoesNotContain(packets, item => string.Equals(item.Kind, "continuity_packet", StringComparison.Ordinal));
    }

    [Fact]
    public void ContinuityPacketActivatesFromCarryForwardEvidenceLinesWhenPrimaryFieldsAreSparse()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspaceWithContinuityCarryForwardEvidenceSignalsOnly();
        WorkspaceRestoreProjection restore = BuildEmptyRestore();

        IReadOnlyList<GovernedPrepPacketSummary> packets = InvokeBuildPrepPackets(workspace, restore);

        GovernedPrepPacketSummary packet = Assert.Single(packets, item => string.Equals(item.Kind, "continuity_packet", StringComparison.Ordinal));
        Assert.False(packet.Reusable);
        Assert.Contains("continuity", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains(packet.EvidenceLines, line => line.Contains("continuity lane remains open", StringComparison.OrdinalIgnoreCase));
    }

    private static IReadOnlyList<string> InvokeBuildTokens(string? queryText)
    {
        MethodInfo method = typeof(CampaignWorkspaceServerPlaneService)
            .GetMethod("BuildPrepLibraryQueryTokens", BindingFlags.NonPublic | BindingFlags.Static)
            ?? throw new InvalidOperationException("BuildPrepLibraryQueryTokens was not found.");

        return Assert.IsAssignableFrom<IReadOnlyList<string>>(method.Invoke(null, [queryText]));
    }

    private static bool InvokeMatches(GovernedPrepPacketSummary packet, IReadOnlyList<string> queryTokens)
    {
        MethodInfo method = typeof(CampaignWorkspaceServerPlaneService)
            .GetMethod("MatchesPrepLibraryQuery", BindingFlags.NonPublic | BindingFlags.Static)
            ?? throw new InvalidOperationException("MatchesPrepLibraryQuery was not found.");

        return Assert.IsType<bool>(method.Invoke(null, [packet, queryTokens]));
    }

    private static GovernedPrepPacketSummary InvokeResolvePrepPacket(CampaignPrepLibrarySummary prepLibrary, string requestedPacketId)
    {
        MethodInfo method = typeof(CampaignWorkspaceServerPlaneService)
            .GetMethod("ResolvePrepPacket", BindingFlags.NonPublic | BindingFlags.Static)
            ?? throw new InvalidOperationException("ResolvePrepPacket was not found.");

        return Assert.IsType<GovernedPrepPacketSummary>(method.Invoke(null, [prepLibrary, requestedPacketId]));
    }

    private static ClaimedDeviceRestoreProjection InvokeResolveTravelPrefetchDevice(
        WorkspaceRestoreProjection restore,
        string requestedInstallationId)
    {
        MethodInfo method = typeof(CampaignWorkspaceServerPlaneService)
            .GetMethod("ResolveTravelPrefetchDevice", BindingFlags.NonPublic | BindingFlags.Static)
            ?? throw new InvalidOperationException("ResolveTravelPrefetchDevice was not found.");

        return Assert.IsType<ClaimedDeviceRestoreProjection>(method.Invoke(null, [restore, requestedInstallationId]));
    }

    private static string InvokeBoundedRecapShelfCategory(PublicationSafeProjection item)
    {
        MethodInfo method = typeof(CampaignWorkspaceServerPlaneService)
            .GetMethod("BoundedRecapShelfCategory", BindingFlags.NonPublic | BindingFlags.Static)
            ?? throw new InvalidOperationException("BoundedRecapShelfCategory was not found.");

        return Assert.IsType<string>(method.Invoke(null, [item]));
    }

    private static bool InvokeSupportsCreatorShelfProjection(PublicationSafeProjection item)
    {
        MethodInfo method = typeof(CampaignWorkspaceServerPlaneService)
            .GetMethod("SupportsCreatorShelfProjection", BindingFlags.NonPublic | BindingFlags.Static)
            ?? throw new InvalidOperationException("SupportsCreatorShelfProjection was not found.");

        return Assert.IsType<bool>(method.Invoke(null, [item]));
    }

    private static IReadOnlyList<CampaignWorkspaceProjection> InvokeCampaignSpineAttachCreatorPublicationPosture(
        IReadOnlyList<CampaignWorkspaceProjection> workspaces,
        IReadOnlyList<CreatorPublicationProjection> creatorPublications)
    {
        MethodInfo method = typeof(CampaignSpineService)
            .GetMethod("AttachCreatorPublicationPosture", BindingFlags.NonPublic | BindingFlags.Static)
            ?? throw new InvalidOperationException("AttachCreatorPublicationPosture was not found.");

        return Assert.IsAssignableFrom<IReadOnlyList<CampaignWorkspaceProjection>>(method.Invoke(null, [workspaces, creatorPublications]));
    }

    private static string InvokeCampaignSpineResolveRosterTransferRequestIdentity(string? identity, string fieldLabel)
    {
        MethodInfo method = typeof(CampaignSpineService)
            .GetMethod("ResolveRosterTransferRequestIdentity", BindingFlags.NonPublic | BindingFlags.Static)
            ?? throw new InvalidOperationException("ResolveRosterTransferRequestIdentity was not found.");

        return Assert.IsType<string>(method.Invoke(null, [identity, fieldLabel]));
    }

    private static IReadOnlyList<CommunitySeasonBoardEntryProjection> InvokeCampaignSpineBuildGroupSeasonBoardEntries(
        IReadOnlyList<CampaignWorkspaceProjection> workspaces)
    {
        MethodInfo method = typeof(CampaignSpineService)
            .GetMethod("BuildGroupSeasonBoardEntries", BindingFlags.NonPublic | BindingFlags.Static)
            ?? throw new InvalidOperationException("BuildGroupSeasonBoardEntries was not found.");

        return Assert.IsAssignableFrom<IReadOnlyList<CommunitySeasonBoardEntryProjection>>(method.Invoke(null, [workspaces]));
    }

    private static IReadOnlyList<string> InvokeCampaignSpineBuildGroupOperatorWatchouts(
        IReadOnlyList<CampaignWorkspaceProjection> workspaces)
    {
        MethodInfo method = typeof(CampaignSpineService)
            .GetMethod("BuildGroupOperatorWatchouts", BindingFlags.NonPublic | BindingFlags.Static)
            ?? throw new InvalidOperationException("BuildGroupOperatorWatchouts was not found.");

        return Assert.IsAssignableFrom<IReadOnlyList<string>>(method.Invoke(null, [workspaces]));
    }

    private static IReadOnlyList<DecisionNotice> InvokeBuildDecisionNotices(
        CampaignWorkspaceProjection workspace,
        CampaignWorkspaceDigestProjection digest,
        IReadOnlyList<SupportCaseDigestViewModel> supportDigests,
        CampaignPrepLibrarySummary prepLibrary)
    {
        MethodInfo method = typeof(CampaignWorkspaceServerPlaneService)
            .GetMethod("BuildDecisionNotices", BindingFlags.NonPublic | BindingFlags.Static)
            ?? throw new InvalidOperationException("BuildDecisionNotices was not found.");

        return Assert.IsAssignableFrom<IReadOnlyList<DecisionNotice>>(method.Invoke(null, [workspace, digest, null, supportDigests, prepLibrary, null]));
    }

    private static IReadOnlyList<SupportClosureCue> InvokeBuildSupportClosures(
        IReadOnlyList<SupportCaseDigestViewModel> supportDigests)
    {
        MethodInfo method = typeof(CampaignWorkspaceServerPlaneService)
            .GetMethod("BuildSupportClosures", BindingFlags.NonPublic | BindingFlags.Static)
            ?? throw new InvalidOperationException("BuildSupportClosures was not found.");

        return Assert.IsAssignableFrom<IReadOnlyList<SupportClosureCue>>(method.Invoke(null, [supportDigests]));
    }

    private static IReadOnlyList<KnownIssueAffectingInstall> InvokeBuildKnownIssues(
        IReadOnlyList<SupportCaseDigestViewModel> supportDigests)
    {
        MethodInfo method = typeof(CampaignWorkspaceServerPlaneService)
            .GetMethod("BuildKnownIssues", BindingFlags.NonPublic | BindingFlags.Static)
            ?? throw new InvalidOperationException("BuildKnownIssues was not found.");

        return Assert.IsAssignableFrom<IReadOnlyList<KnownIssueAffectingInstall>>(method.Invoke(null, [supportDigests]));
    }

    private static CampaignWorkspaceDigestProjection BuildWorkspaceDigest(CampaignWorkspaceProjection workspace)
        => new(
            WorkspaceId: workspace.WorkspaceId,
            CampaignId: workspace.CampaignId,
            CampaignName: workspace.CampaignName,
            ReturnSummary: workspace.ReturnSummary,
            RuleEnvironmentSummary: $"{workspace.RuleEnvironment.OwnerScope} · {workspace.RuleEnvironment.CompatibilityFingerprint}",
            DeviceRoleSummary: "workstation on linux/avalonia (stable)",
            SupportClosureSummary: "Support closure stays attached to release-aware install truth.",
            ActiveSceneSummary: workspace.ActiveSceneSummary,
            NextSafeAction: workspace.NextSafeAction ?? "Open shared campaign view.",
            ReadinessHighlights: [],
            Watchouts: [],
            UpdatedAtUtc: DateTimeOffset.Parse("2026-04-04T00:00:00Z"));

    private static CampaignPrepLibrarySummary BuildEmptyPrepLibrary()
        => new(
            Summary: "No governed prep packet is compiled yet for this shared campaign view.",
            BindingSummary: "Packets stay bound to the shared campaign return lane.",
            SearchSummary: "Search tokens compile from campaign and restore context.",
            ReusablePacketCount: 0,
            SearchablePacketCount: 0,
            Packets: []);

    private static SupportCaseDigestViewModel BuildSupportCaseDigest(
        string caseId,
        string releaseProgressSummary,
        bool reporterActionNeeded = false,
        bool canVerifyFix = false)
        => new(
            CaseId: caseId,
            Title: $"Support case {caseId}",
            Summary: "Support case summary.",
            StatusLabel: "In progress",
            StageLabel: "Needs follow-through",
            NextSafeAction: "Open support case details and follow through.",
            ClosureSummary: "Closure remains pending follow-through.",
            VerificationSummary: "Verification lane is active.",
            DetailHref: $"/account/support/{Uri.EscapeDataString(caseId)}",
            PrimaryActionLabel: "Open support case",
            PrimaryActionHref: $"/account/support/{Uri.EscapeDataString(caseId)}",
            UpdatedLabel: "updated just now",
            FixedReleaseLabel: null,
            AffectedInstallSummary: "Affects workstation on linux/avalonia (stable).",
            FollowUpLaneSummary: "Follow-up remains on governed lane.",
            ReleaseProgressSummary: releaseProgressSummary,
            ReporterActionNeeded: reporterActionNeeded,
            CanVerifyFix: canVerifyFix,
            InstallReadinessSummary: "Install readiness is known.",
            FixReadyOnLinkedInstall: canVerifyFix,
            NeedsInstallUpdate: false,
            NeedsLinkedInstall: false);

    private static CampaignWorkspaceDigestProjection InvokeCampaignSpineBuildWorkspaceDigest(
        AccountCampaignSummary summary,
        CampaignWorkspaceProjection workspace)
    {
        MethodInfo method = typeof(CampaignSpineService)
            .GetMethod("BuildWorkspaceDigest", BindingFlags.NonPublic | BindingFlags.Static)
            ?? throw new InvalidOperationException("BuildWorkspaceDigest was not found.");

        return Assert.IsType<CampaignWorkspaceDigestProjection>(method.Invoke(null, [summary, workspace]));
    }

    private static WorkspaceStateSummary InvokeBuildWorkspaceStateSummary(
        CampaignWorkspaceProjection workspace,
        IReadOnlyList<RuleEnvironmentHealthCue> ruleEnvironmentHealth,
        IReadOnlyList<ContinuityConflictCue> continuityConflicts,
        IReadOnlyList<SupportCaseDigestViewModel> supportDigests,
        TravelModeReadinessSummary travelMode,
        object nextSafeAction)
    {
        MethodInfo method = typeof(CampaignWorkspaceServerPlaneService)
            .GetMethod("BuildWorkspaceStateSummary", BindingFlags.NonPublic | BindingFlags.Static)
            ?? throw new InvalidOperationException("BuildWorkspaceStateSummary was not found.");

        return Assert.IsType<WorkspaceStateSummary>(method.Invoke(null, [workspace, null, ruleEnvironmentHealth, continuityConflicts, supportDigests, travelMode, nextSafeAction]));
    }

    private static object InvokeBuildNextSafeActionCue(CampaignWorkspaceProjection workspace)
    {
        MethodInfo method = typeof(CampaignWorkspaceServerPlaneService)
            .GetMethod("BuildNextSafeActionCue", BindingFlags.NonPublic | BindingFlags.Static)
            ?? throw new InvalidOperationException("BuildNextSafeActionCue was not found.");

        object? cue = method.Invoke(null, [workspace, null, Array.Empty<SupportCaseDigestViewModel>()]);
        return cue ?? throw new InvalidOperationException("BuildNextSafeActionCue returned null.");
    }

    private static string InvokeCampaignSpineResolveWorkspaceNextSafeAction(
        CampaignProjection campaign,
        WorkspaceRestoreProjection restore,
        IReadOnlyList<PublicationSafeProjection> recapShelf,
        IReadOnlyList<CampaignReadinessCue> readinessCues,
        RunProjection? leadRun,
        SceneProjection? activeScene,
        ObjectiveProjection? leadObjective)
    {
        MethodInfo method = typeof(CampaignSpineService)
            .GetMethod("ResolveWorkspaceNextSafeAction", BindingFlags.NonPublic | BindingFlags.Static)
            ?? throw new InvalidOperationException("ResolveWorkspaceNextSafeAction was not found.");

        return Assert.IsType<string>(method.Invoke(null,
        [
            campaign,
            restore,
            recapShelf,
            readinessCues,
            leadRun,
            activeScene,
            leadObjective
        ]));
    }

    private static FirstPlayableSessionProjection? InvokeCampaignSpineBuildFirstPlayableSession(
        CampaignProjection campaign,
        WorkspaceRestoreProjection restore,
        IReadOnlyList<CampaignReadinessCue> readinessCues,
        IReadOnlyList<CrewProjection> workspaceCrews,
        IReadOnlyList<RunnerDossierProjection> workspaceDossiers,
        RunProjection? leadRun,
        SceneProjection? activeScene,
        ObjectiveProjection? leadObjective)
    {
        MethodInfo method = typeof(CampaignSpineService)
            .GetMethod("BuildFirstPlayableSession", BindingFlags.NonPublic | BindingFlags.Static)
            ?? throw new InvalidOperationException("BuildFirstPlayableSession was not found.");

        return (FirstPlayableSessionProjection?)method.Invoke(null,
        [
            campaign,
            restore,
            readinessCues,
            workspaceCrews,
            workspaceDossiers,
            leadRun,
            activeScene,
            leadObjective,
            "Keep return loop on governed lane.",
            Array.Empty<GovernedPrepLaunchProjection>(),
            Array.Empty<TravelPrefetchReceiptProjection>(),
            Array.Empty<AftermathRecapPackageProjection>()
        ]);
    }

    private static IReadOnlyList<CreatorPublicationProjection> InvokeCampaignSpineBuildCreatorPublications(
        IReadOnlyList<CampaignWorkspaceProjection> workspaces)
    {
        MethodInfo method = typeof(CampaignSpineService)
            .GetMethod("BuildCreatorPublications", BindingFlags.NonPublic | BindingFlags.Static)
            ?? throw new InvalidOperationException("BuildCreatorPublications was not found.");

        return Assert.IsAssignableFrom<IReadOnlyList<CreatorPublicationProjection>>(method.Invoke(null, [workspaces, Array.Empty<RunnerDossierProjection>(), Array.Empty<BuildLabHandoffProjection>()]));
    }

    private static IReadOnlyList<PublicationSafeProjection> InvokeCampaignSpineEnrichWorkspaceRecapShelf(
        CampaignProjection campaign,
        string workspaceId,
        IReadOnlyList<PublicationSafeProjection> recapShelf)
    {
        MethodInfo method = typeof(CampaignSpineService)
            .GetMethod("EnrichWorkspaceRecapShelf", BindingFlags.NonPublic | BindingFlags.Static)
            ?? throw new InvalidOperationException("EnrichWorkspaceRecapShelf was not found.");

        return Assert.IsAssignableFrom<IReadOnlyList<PublicationSafeProjection>>(method.Invoke(
            null,
            [
                campaign,
                workspaceId,
                recapShelf,
                "Keep return loop on governed lane."
            ]));
    }

    private static NextSessionCarryForwardProjection? InvokeCampaignSpineBuildNextSessionCarryForward(
        CampaignProjection campaign,
        IReadOnlyList<AftermathRecapPackageProjection> aftermathPackages)
        => InvokeCampaignSpineBuildNextSessionCarryForward(
            campaign,
            Array.Empty<CampaignConsequenceProjection>(),
            Array.Empty<GovernedPrepLaunchProjection>(),
            Array.Empty<TravelPrefetchReceiptProjection>(),
            aftermathPackages);

    private static NextSessionCarryForwardProjection? InvokeCampaignSpineBuildNextSessionCarryForward(
        CampaignProjection campaign,
        IReadOnlyList<CampaignConsequenceProjection> consequences,
        IReadOnlyList<GovernedPrepLaunchProjection> prepLaunches,
        IReadOnlyList<TravelPrefetchReceiptProjection> travelPrefetchReceipts,
        IReadOnlyList<AftermathRecapPackageProjection> aftermathPackages,
        RunProjection? leadRun = null,
        SceneProjection? activeScene = null,
        ObjectiveProjection? leadObjective = null)
    {
        MethodInfo method = typeof(CampaignSpineService)
            .GetMethod("BuildNextSessionCarryForward", BindingFlags.NonPublic | BindingFlags.Static)
            ?? throw new InvalidOperationException("BuildNextSessionCarryForward was not found.");

        return (NextSessionCarryForwardProjection?)method.Invoke(null,
        [
            campaign,
            "Keep return loop on governed lane.",
            leadRun,
            activeScene,
            leadObjective,
            consequences,
            prepLaunches,
            travelPrefetchReceipts,
            aftermathPackages
        ]);
    }

    private static CampaignMemoryProjection? InvokeCampaignSpineBuildCampaignMemory(
        CampaignProjection campaign,
        IReadOnlyList<AftermathRecapPackageProjection> aftermathPackages)
        => InvokeCampaignSpineBuildCampaignMemory(
            campaign,
            Array.Empty<CampaignConsequenceProjection>(),
            Array.Empty<RosterTransferProjection>(),
            Array.Empty<GovernedPrepLaunchProjection>(),
            Array.Empty<TravelPrefetchReceiptProjection>(),
            aftermathPackages,
            null);

    private static CampaignMemoryProjection? InvokeCampaignSpineBuildCampaignMemory(
        CampaignProjection campaign,
        IReadOnlyList<CampaignConsequenceProjection> consequences,
        IReadOnlyList<RosterTransferProjection> rosterTransfers,
        IReadOnlyList<GovernedPrepLaunchProjection> prepLaunches,
        IReadOnlyList<TravelPrefetchReceiptProjection> travelPrefetchReceipts,
        IReadOnlyList<AftermathRecapPackageProjection> aftermathPackages,
        NextSessionCarryForwardProjection? carryForward)
    {
        MethodInfo method = typeof(CampaignSpineService)
            .GetMethod("BuildCampaignMemory", BindingFlags.NonPublic | BindingFlags.Static)
            ?? throw new InvalidOperationException("BuildCampaignMemory was not found.");

        return (CampaignMemoryProjection?)method.Invoke(null,
        [
            campaign,
            "Keep return loop on governed lane.",
            null,
            null,
            null,
            consequences,
            rosterTransfers,
            prepLaunches,
            travelPrefetchReceipts,
            aftermathPackages,
            carryForward
        ]);
    }

    private static IReadOnlyList<WorkspaceChangePacketProjection> InvokeCampaignSpineBuildWorkspaceChangePackets(
        CampaignProjection campaign,
        IReadOnlyList<AftermathRecapPackageProjection> aftermathPackages)
        => InvokeCampaignSpineBuildWorkspaceChangePackets(campaign, [], aftermathPackages, null);

    private static IReadOnlyList<dynamic> InvokeCampaignSpineBuildWorkspaceRulesNavigatorDiffs(
        CampaignWorkspaceProjection workspace)
    {
        MethodInfo method = typeof(CampaignSpineService)
            .GetMethod("BuildWorkspaceRulesNavigatorDiffs", BindingFlags.NonPublic | BindingFlags.Static)
            ?? throw new InvalidOperationException("BuildWorkspaceRulesNavigatorDiffs was not found.");
        object? value = method.Invoke(null, [workspace]);
        IEnumerable<object> projection = Assert.IsAssignableFrom<IEnumerable<object>>(value);
        return projection.Cast<dynamic>().ToArray();
    }

    private static IReadOnlyList<WorkspaceChangePacketProjection> InvokeCampaignSpineBuildWorkspaceChangePackets(
        CampaignProjection campaign,
        IReadOnlyList<PublicationSafeProjection> recapShelf,
        IReadOnlyList<AftermathRecapPackageProjection> aftermathPackages,
        NextSessionCarryForwardProjection? carryForward)
        => InvokeCampaignSpineBuildWorkspaceChangePackets(
            campaign,
            recapShelf,
            aftermathPackages,
            carryForward,
            [],
            [],
            []);

    private static IReadOnlyList<WorkspaceChangePacketProjection> InvokeCampaignSpineBuildWorkspaceChangePackets(
        CampaignProjection campaign,
        IReadOnlyList<PublicationSafeProjection> recapShelf,
        IReadOnlyList<AftermathRecapPackageProjection> aftermathPackages,
        NextSessionCarryForwardProjection? carryForward,
        IReadOnlyList<RosterTransferProjection> rosterTransfers,
        IReadOnlyList<GovernedPrepLaunchProjection> prepLaunches,
        IReadOnlyList<TravelPrefetchReceiptProjection> travelPrefetchReceipts,
        RunProjection? leadRun = null,
        SceneProjection? activeScene = null,
        ObjectiveProjection? leadObjective = null)
    {
        MethodInfo method = typeof(CampaignSpineService)
            .GetMethod("BuildWorkspaceChangePackets", BindingFlags.NonPublic | BindingFlags.Static)
            ?? throw new InvalidOperationException("BuildWorkspaceChangePackets was not found.");

        return Assert.IsAssignableFrom<IReadOnlyList<WorkspaceChangePacketProjection>>(method.Invoke(null,
        [
            campaign,
            recapShelf,
            leadRun,
            activeScene,
            leadObjective,
            rosterTransfers,
            prepLaunches,
            travelPrefetchReceipts,
            aftermathPackages,
            carryForward
        ]));
    }

    private static IReadOnlyList<RecapShelfEntry> InvokeBuildRecapShelf(CampaignWorkspaceProjection workspace)
        => InvokeBuildRecapShelf(workspace, Array.Empty<CreatorPublicationProjection>());

    private static IReadOnlyList<RecapShelfEntry> InvokeBuildRecapShelf(
        CampaignWorkspaceProjection workspace,
        IReadOnlyList<CreatorPublicationProjection> creatorPublications)
    {
        MethodInfo method = typeof(CampaignWorkspaceServerPlaneService)
            .GetMethod("BuildRecapShelf", BindingFlags.NonPublic | BindingFlags.Static)
            ?? throw new InvalidOperationException("BuildRecapShelf was not found.");

        return Assert.IsAssignableFrom<IReadOnlyList<RecapShelfEntry>>(method.Invoke(null, [workspace, creatorPublications]));
    }

    private static PublicationSafeProjection BuildPublicationSafeProjection(string kind)
        => new(
            ProjectionId: $"publication-{kind}",
            Kind: kind,
            Label: "Publication label",
            Summary: "Publication summary");

    private static IReadOnlyList<GovernedPrepPacketSummary> InvokeBuildPrepPackets(
        CampaignWorkspaceProjection workspace,
        WorkspaceRestoreProjection restore)
        => InvokeBuildPrepPackets(workspace, restore, null);

    private static IReadOnlyList<GovernedPrepPacketSummary> InvokeBuildPrepPackets(
        CampaignWorkspaceProjection workspace,
        WorkspaceRestoreProjection restore,
        RunProjection? leadRun)
    {
        MethodInfo method = typeof(CampaignWorkspaceServerPlaneService)
            .GetMethod("BuildPrepPackets", BindingFlags.NonPublic | BindingFlags.Static)
            ?? throw new InvalidOperationException("BuildPrepPackets was not found.");

        return Assert.IsAssignableFrom<IReadOnlyList<GovernedPrepPacketSummary>>(method.Invoke(null, [workspace, restore, leadRun]));
    }

    private static CampaignWorkspaceSummary InvokeBuildCampaignWorkspaceSummary(
        CampaignWorkspaceProjection workspace,
        WorkspaceRestoreProjection restore)
    {
        MethodInfo method = typeof(CampaignWorkspaceServerPlaneService)
            .GetMethod("BuildCampaignWorkspaceSummary", BindingFlags.NonPublic | BindingFlags.Static)
            ?? throw new InvalidOperationException("BuildCampaignWorkspaceSummary was not found.");

        return Assert.IsType<CampaignWorkspaceSummary>(method.Invoke(null, [workspace, null, restore]));
    }

    private static RosterReadinessSummary InvokeBuildRosterReadinessSummary(
        CampaignWorkspaceProjection workspace)
    {
        MethodInfo method = typeof(CampaignWorkspaceServerPlaneService)
            .GetMethod("BuildRosterReadinessSummary", BindingFlags.NonPublic | BindingFlags.Static)
            ?? throw new InvalidOperationException("BuildRosterReadinessSummary was not found.");

        return Assert.IsType<RosterReadinessSummary>(method.Invoke(null, [workspace]));
    }

    private static TravelModeReadinessSummary BuildTravelModeReadinessSummary()
        => new(
            Status: "ready",
            Summary: "Travel readiness is green.",
            PrefetchInventorySummary: "Prefetch inventory is attached.",
            ClaimedDeviceCount: 1,
            TravelReadyDeviceCount: 1,
            Devices: [],
            Boundaries: []);

    private static RunboardSummary? InvokeBuildRunboardSummary(
        CampaignWorkspaceProjection workspace,
        RunProjection? leadRun)
    {
        MethodInfo method = typeof(CampaignWorkspaceServerPlaneService)
            .GetMethod("BuildRunboardSummary", BindingFlags.NonPublic | BindingFlags.Static)
            ?? throw new InvalidOperationException("BuildRunboardSummary was not found.");

        return (RunboardSummary?)method.Invoke(null, [workspace, leadRun]);
    }

    private static int IndexOfPacketKind(IReadOnlyList<GovernedPrepPacketSummary> packets, string kind)
        => packets
            .Select(static (item, index) => new { item.Kind, index })
            .Where(item => string.Equals(item.Kind, kind, StringComparison.Ordinal))
            .Select(static item => item.index)
            .DefaultIfEmpty(-1)
            .First();

    private static bool InvokeIsTravelReadyDevice(ClaimedDeviceRestoreProjection device)
    {
        MethodInfo method = typeof(CampaignWorkspaceServerPlaneService)
            .GetMethod("IsTravelReadyDevice", BindingFlags.NonPublic | BindingFlags.Static)
            ?? throw new InvalidOperationException("IsTravelReadyDevice was not found.");

        return Assert.IsType<bool>(method.Invoke(null, [device]));
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithRosterAndAftermath()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        RosterTransferProjection transfer = new(
            TransferId: "transfer-1",
            DossierId: "dossier-1",
            RunnerHandle: "Ghostline",
            PreviousOwnerUserId: "user-a",
            CurrentOwnerUserId: "user-b",
            SourceGroupId: "group-a",
            SourceGroupName: "Night Shift",
            SourceCampaignId: "campaign-a",
            SourceCampaignName: "Neon Cradle",
            SourceCrewId: "crew-a",
            SourceCrewName: "Wardens",
            TargetGroupId: "group-b",
            TargetGroupName: "Aftermath Desk",
            TargetCampaignId: "campaign-b",
            TargetCampaignName: "Season Ops",
            TargetCrewId: "crew-b",
            TargetCrewName: "Organizers",
            InitiatedByUserId: "gm-1",
            Summary: "Moved Ghostline into season operations roster lane.",
            AuditLines: ["Roster movement receipt captured for season operations."],
            Receipts: [],
            TransferredAtUtc: now);

        AftermathRecapPackageProjection aftermath = new(
            PackageId: "package-1",
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            RunId: "run-1",
            RunTitle: "Dockyard pressure test",
            PackageKind: "downtime_brief",
            Title: "Downtime brief",
            Summary: "Downtime consequences and return cues are published for next session.",
            ArtifactId: "artifact-1",
            EvidenceLines: ["Heat posture and contact fallout captured."],
            InitiatedByUserId: "gm-1",
            GeneratedAtUtc: now);

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            RosterTransfers: [transfer],
            AftermathPackages: [aftermath]);
    }

    private static CampaignProjection BuildCampaignProjection(CampaignWorkspaceProjection workspace)
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        return new CampaignProjection(
            CampaignId: workspace.CampaignId,
            GroupId: "group-a",
            Name: workspace.CampaignName,
            Status: "active",
            Visibility: workspace.Visibility,
            Summary: "Campaign continuity remains attached to one governed lane.",
            RuleEnvironment: workspace.RuleEnvironment,
            ActiveRunId: null,
            CrewIds: [],
            DossierIds: [],
            RunIds: [],
            LatestContinuity: null,
            CreatedAtUtc: now,
            UpdatedAtUtc: now);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithEventControls()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        var carryForward = new NextSessionCarryForwardProjection(
            CarryForwardId: "carry-1",
            Label: "Next session carry-forward",
            Summary: "Season event controls and return windows are staged for the next run.",
            ReturnSummary: "Return window remains governed from workspace state.",
            NextSafeAction: "Open event controls before launching the next prep lane.",
            EvidenceLines: ["Carry-forward receipt captured from the latest continuity lane."],
            UpdatedAtUtc: now.AddMinutes(5));

        var changePacket = new WorkspaceChangePacketProjection(
            PacketId: "packet-1",
            Kind: "prep_launch",
            Label: "GM prep launch",
            Summary: "Event board packet launched for season operations.",
            UpdatedAtUtc: now.AddMinutes(3));

        var consequence = new CampaignConsequenceProjection(
            ConsequenceId: "consequence-1",
            Kind: "heat",
            Label: "Heat posture",
            State: "elevated",
            Summary: "Event pressure remains elevated until the return loop is confirmed.",
            EvidenceLines: ["Heat review line captured for event control."],
            Receipts:
            [
                new CampaignConsequenceReceipt(
                    ReceiptId: "objective-1",
                    SourceKind: "objective",
                    Summary: "Open pressure objective still active.")
            ],
            UpdatedAtUtc: now.AddMinutes(4));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [changePacket],
            Consequences: [consequence],
            NextSessionCarryForward: carryForward);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithCampaignMemorySignals()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        CampaignMemoryProjection campaignMemory = new(
            MemoryId: "memory-1",
            Label: "Long-lived memory ledger",
            Summary: "Long-lived campaign memory keeps season outcomes and contact fallout reviewable.",
            ReturnSummary: "Memory return lane stays attached to the same governed workspace.",
            NextSafeAction: "Review memory ledger before next session prep.",
            EvidenceLines: ["Long-lived memory evidence remains attached to recap and consequence receipts."],
            UpdatedAtUtc: now.AddMinutes(4));
        WorkspaceChangePacketProjection memoryChange = new(
            PacketId: "packet-1",
            Kind: "campaign_memory_update",
            Label: "Campaign memory update",
            Summary: "Campaign memory ledger updated after downtime reconciliation.",
            UpdatedAtUtc: now.AddMinutes(3));
        CampaignConsequenceProjection memoryConsequence = new(
            ConsequenceId: "consequence-1",
            Kind: "campaign_memory",
            Label: "Memory continuity watch",
            State: "active",
            Summary: "Long-lived memory continuity remains active for next-session follow-through.",
            EvidenceLines: ["Memory continuity receipt linked to governed recap package."],
            Receipts:
            [
                new CampaignConsequenceReceipt(
                    ReceiptId: "receipt-1",
                    SourceKind: "campaign_memory",
                    Summary: "Memory ledger receipt captured from shared campaign board.")
            ],
            UpdatedAtUtc: now.AddMinutes(2));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [memoryChange],
            Consequences: [memoryConsequence],
            CampaignMemory: campaignMemory);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithCampaignReturnSignals()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        PublicationSafeProjection recap = new(
            ProjectionId: "recap-1",
            Kind: "session_recap",
            Label: "After action diary",
            Summary: "Diary recap records downtime outcomes and next-session obligations.");
        WorkspaceChangePacketProjection changePacket = new(
            PacketId: "packet-1",
            Kind: "next_session_carry_forward",
            Label: "Carry-forward packet",
            Summary: "Carry-forward packet keeps diary and contact follow-through on one lane.",
            UpdatedAtUtc: now.AddMinutes(3));
        CampaignConsequenceProjection contactConsequence = new(
            ConsequenceId: "consequence-1",
            Kind: "contact",
            Label: "Fixer pressure",
            State: "active",
            Summary: "Contact obligations remain active in the return loop.",
            EvidenceLines: ["Contact diary update captured from the latest recap."],
            Receipts:
            [
                new CampaignConsequenceReceipt(
                    ReceiptId: "receipt-1",
                    SourceKind: "contact",
                    Summary: "Contact relationship changed after downtime.")
            ],
            UpdatedAtUtc: now.AddMinutes(4));
        CampaignConsequenceProjection heatConsequence = new(
            ConsequenceId: "consequence-2",
            Kind: "heat",
            Label: "Street heat",
            State: "elevated",
            Summary: "Operational heat stays elevated until the next session opens.",
            EvidenceLines: ["Heat trend remains tied to the same return lane."],
            Receipts:
            [
                new CampaignConsequenceReceipt(
                    ReceiptId: "receipt-2",
                    SourceKind: "objective",
                    Summary: "Open objective keeps pressure elevated.")
            ],
            UpdatedAtUtc: now.AddMinutes(5));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [recap],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [changePacket],
            Consequences: [contactConsequence, heatConsequence]);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithAftermathSignalsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        AftermathRecapPackageProjection aftermath = new(
            PackageId: "package-1",
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            RunId: "run-1",
            RunTitle: "Dockyard pressure test",
            PackageKind: "downtime_brief",
            Title: "Aftermath downtime brief",
            Summary: "Aftermath summary captures downtime obligations for return.",
            ArtifactId: "artifact-1",
            EvidenceLines: ["Aftermath heat and contact fallout captured for return."],
            InitiatedByUserId: "gm-1",
            GeneratedAtUtc: now.AddMinutes(6));

        WorkspaceChangePacketProjection aftermathChange = new(
            PacketId: "packet-1",
            Kind: "aftermath",
            Label: "Aftermath change packet",
            Summary: "Aftermath change remains governed on the return lane.",
            UpdatedAtUtc: now.AddMinutes(5));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [aftermathChange],
            Consequences: [],
            AftermathPackages: [aftermath]);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithAftermathChangeSignalsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        WorkspaceChangePacketProjection aftermathChange = new(
            PacketId: "packet-1",
            Kind: "downtime_brief",
            Label: "Downtime signal",
            Summary: "Downtime change packet keeps aftermath continuity visible before package receipts land.",
            UpdatedAtUtc: now.AddMinutes(4));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [aftermathChange],
            Consequences: [],
            AftermathPackages: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithAftermathSignalLabelsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        WorkspaceChangePacketProjection aftermathChange = new(
            PacketId: "packet-1",
            Kind: "downtime_brief",
            Label: "Downtime label",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(4));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [aftermathChange],
            Consequences: [],
            AftermathPackages: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithAftermathSparseSignalKindsAndLabelsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        WorkspaceChangePacketProjection aftermathChange = new(
            PacketId: "packet-1",
            Kind: "",
            Label: "Downtime label",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(4));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [aftermathChange],
            Consequences: [],
            AftermathPackages: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithAftermathSignalKindsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        WorkspaceChangePacketProjection aftermathChange = new(
            PacketId: "packet-1",
            Kind: "downtime_brief",
            Label: "",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(4));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [aftermathChange],
            Consequences: [],
            AftermathPackages: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithAftermathRecapKindsOnly()
    {
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        PublicationSafeProjection recap = new(
            ProjectionId: "recap-1",
            Kind: "downtime_brief",
            Label: "",
            Summary: "");

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [recap],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [],
            Consequences: [],
            AftermathPackages: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithAftermathRecapLabelOnly()
    {
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        PublicationSafeProjection recap = new(
            ProjectionId: "recap-1",
            Kind: "",
            Label: "Downtime recap label",
            Summary: "");

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [recap],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [],
            Consequences: [],
            AftermathPackages: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithAftermathRecapKindsAndVerbosePackage()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        PublicationSafeProjection recap = new(
            ProjectionId: "recap-1",
            Kind: "downtime_brief",
            Label: "",
            Summary: "");
        AftermathRecapPackageProjection package = new(
            PackageId: "package-1",
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            RunId: "run-1",
            RunTitle: "Dockyard Pressure Test",
            PackageKind: "aftermath",
            Title: "Verbose aftermath package title line",
            Summary: "Verbose aftermath package summary line",
            ArtifactId: "artifact-1",
            EvidenceLines:
            [
                "Verbose aftermath evidence line one.",
                "Verbose aftermath evidence line two."
            ],
            InitiatedByUserId: "gm-1",
            GeneratedAtUtc: now);

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [recap],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [],
            Consequences: [],
            AftermathPackages: [package]);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithAftermathRecapKindsAndVerboseRecapEvidence()
    {
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        PublicationSafeProjection recapOne = new(
            ProjectionId: "recap-1",
            Kind: "downtime_brief",
            Label: "",
            Summary: "Verbose downtime recap lane summary line one.");
        PublicationSafeProjection recapTwo = new(
            ProjectionId: "recap-2",
            Kind: "downtime_brief",
            Label: "",
            Summary: "Verbose downtime recap lane summary line two.");
        PublicationSafeProjection recapThree = new(
            ProjectionId: "recap-3",
            Kind: "downtime_brief",
            Label: "",
            Summary: "Verbose downtime recap lane summary line three.");
        PublicationSafeProjection recapFour = new(
            ProjectionId: "recap-4",
            Kind: "downtime_brief",
            Label: "",
            Summary: "Verbose downtime recap lane summary line four.");

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [recapOne, recapTwo, recapThree, recapFour],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [],
            Consequences: [],
            AftermathPackages: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithRelationshipChangeSignalsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        WorkspaceChangePacketProjection relationshipChange = new(
            PacketId: "packet-1",
            Kind: "heat_relationship_shift",
            Label: "Relationship change",
            Summary: "Relationship update keeps contact and heat posture on the return lane before consequence receipts land.",
            UpdatedAtUtc: now.AddMinutes(4));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [relationshipChange],
            Consequences: [],
            AftermathPackages: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithFavorAndLoyaltyRelationshipSignalsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        WorkspaceChangePacketProjection relationshipChange = new(
            PacketId: "packet-1",
            Kind: "contact_favor_shift",
            Label: "Fixer favor shift",
            Summary: "Loyalty changed after downtime follow-through and stays on the return lane.",
            UpdatedAtUtc: now.AddMinutes(4));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [relationshipChange],
            Consequences: [],
            AftermathPackages: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithConnectionRelationshipSignalsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        WorkspaceChangePacketProjection relationshipChange = new(
            PacketId: "packet-1",
            Kind: "contact_connection_shift",
            Label: "Fixer connection shift",
            Summary: "Connection changed after downtime fallout and stays on the return lane.",
            UpdatedAtUtc: now.AddMinutes(4));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [relationshipChange],
            Consequences: [],
            AftermathPackages: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithStreetCredAndPublicAwarenessRelationshipSignalsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        WorkspaceChangePacketProjection relationshipChange = new(
            PacketId: "packet-1",
            Kind: "street_cred_shift",
            Label: "Street cred shift",
            Summary: "Public awareness changed after downtime fallout and stays on the return lane.",
            UpdatedAtUtc: now.AddMinutes(4));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [relationshipChange],
            Consequences: [],
            AftermathPackages: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithCompactStreetCredAndPublicAwarenessRelationshipSignalsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        WorkspaceChangePacketProjection relationshipChange = new(
            PacketId: "packet-1",
            Kind: "streetcred_shift",
            Label: "Streetcred shift",
            Summary: "Publicawareness changed after downtime fallout and stays on the return lane.",
            UpdatedAtUtc: now.AddMinutes(4));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [relationshipChange],
            Consequences: [],
            AftermathPackages: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithPrepLaunchAndTravelPrefetchReceipts()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        GovernedPrepLaunchProjection prepLaunch = new(
            LaunchId: "launch-1",
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            PacketId: "scene:workspace-1",
            PacketKind: "scene_packet",
            PacketTitle: "Dockyard scene packet",
            TargetRunId: "run-1",
            TargetRunTitle: "Dockyard pressure test",
            TargetSceneId: "scene-1",
            TargetSceneTitle: "Dockyard checkpoint",
            InitiatedByUserId: "gm-1",
            Summary: "GM launched governed scene packet for the next table run.",
            AuditLines: ["Prep launch receipt captured on the account audit lane."],
            LaunchedAtUtc: now.AddMinutes(6));

        TravelPrefetchReceiptProjection prefetch = new(
            ReceiptId: "prefetch-1",
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            InstallationId: "install-1",
            DeviceRole: "travel_cache",
            Platform: "ios",
            HeadId: "mobile",
            Channel: "preview",
            PrefetchSummary: "Travel prefetch staged for the next session return loop.",
            InventoryLines: ["Staged dossier, campaign, and prep packet inventory for travel mode."],
            Boundaries: ["Install-local secrets remain local and are never synced."],
            InitiatedByUserId: "gm-1",
            StagedAtUtc: now.AddMinutes(7));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            PrepLaunches: [prepLaunch],
            TravelPrefetches: [prefetch]);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithSparseOpsReceipts()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        ObjectiveProjection objective = new(
            ObjectiveId: "objective-1",
            Title: "Season operation checkpoint",
            Status: "open",
            Pressure: "medium",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(2));

        RunProjection run = new(
            RunId: "run-1",
            CampaignId: "campaign-a",
            Title: "Dockyard pressure test",
            Status: "active",
            Summary: "Current run remains active.",
            ActiveSceneId: null,
            Objectives: [objective],
            Scenes: [],
            LatestContinuity: null,
            CreatedAtUtc: now.AddDays(-1),
            UpdatedAtUtc: now.AddMinutes(3));

        GovernedPrepLaunchProjection prepLaunch = new(
            LaunchId: "launch-1",
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            PacketId: "scene:workspace-1",
            PacketKind: "scene_packet",
            PacketTitle: "",
            TargetRunId: "run-1",
            TargetRunTitle: "",
            TargetSceneId: "scene-1",
            TargetSceneTitle: "",
            InitiatedByUserId: "gm-1",
            Summary: "",
            AuditLines: [],
            LaunchedAtUtc: now.AddMinutes(6));

        TravelPrefetchReceiptProjection prefetch = new(
            ReceiptId: "prefetch-1",
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            InstallationId: "install-1",
            DeviceRole: "travel_cache",
            Platform: "ios",
            HeadId: "mobile",
            Channel: "preview",
            PrefetchSummary: "",
            InventoryLines: [],
            Boundaries: [],
            InitiatedByUserId: "gm-1",
            StagedAtUtc: now.AddMinutes(7));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [run],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            PrepLaunches: [prepLaunch],
            TravelPrefetches: [prefetch]);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithCampaignReturnVariantSignalsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        WorkspaceChangePacketProjection returnVariant = new(
            PacketId: "packet-1",
            Kind: "campaign_return_window",
            Label: "Return window variant",
            Summary: "Return window variant packet keeps next-session reopen cues governed.",
            UpdatedAtUtc: now.AddMinutes(4));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [returnVariant],
            Consequences: [],
            AftermathPackages: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithCampaignReturningSessionLoopMentionsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        WorkspaceChangePacketProjection returningSignal = new(
            PacketId: "packet-campaign-returning-session-loop-1",
            Kind: "status_note",
            Label: "Campaign returning session loop",
            Summary: "Carry-forward remains bounded to the shared return lane.",
            UpdatedAtUtc: now.AddMinutes(4));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-campaign-returning-session-loop-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [returningSignal],
            Consequences: [],
            AftermathPackages: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithCampaignDiaryVariantSignalsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        WorkspaceChangePacketProjection diaryVariant = new(
            PacketId: "packet-1",
            Kind: "journal_diary_update",
            Label: "Diary variant update",
            Summary: "Diary update keeps downtime follow-through visible before recap receipts land.",
            UpdatedAtUtc: now.AddMinutes(4));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [diaryVariant],
            Consequences: [],
            AftermathPackages: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithCampaignReturnRelationshipConsequenceVariantsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        CampaignConsequenceProjection heatVariant = new(
            ConsequenceId: "consequence-1",
            Kind: "heat_pressure_lane",
            Label: "Heat pressure",
            State: "elevated",
            Summary: "Heat pressure remains on the return lane while diary receipts catch up.",
            EvidenceLines: ["Heat pressure stayed governed for return-loop reopen."],
            Receipts: [],
            UpdatedAtUtc: now.AddMinutes(3));
        CampaignConsequenceProjection contactVariant = new(
            ConsequenceId: "consequence-2",
            Kind: "contact_obligation_lane",
            Label: "Fixer pressure",
            State: "active",
            Summary: "Contact obligation remains active in the same return continuity lane.",
            EvidenceLines: ["Fixer pressure remains linked to next-session return posture."],
            Receipts: [],
            UpdatedAtUtc: now.AddMinutes(4));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [],
            Consequences: [heatVariant, contactVariant],
            AftermathPackages: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithCampaignReturnRelationshipSignalVariantsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        WorkspaceChangePacketProjection heatPressureLane = new(
            PacketId: "packet-1",
            Kind: "heat_pressure_lane",
            Label: "Heat pressure lane",
            Summary: "Heat pressure remains attached to the campaign return lane before consequence receipts land.",
            UpdatedAtUtc: now.AddMinutes(3));
        WorkspaceChangePacketProjection contactObligationLane = new(
            PacketId: "packet-2",
            Kind: "contact_obligation_lane",
            Label: "Fixer obligation lane",
            Summary: "Fixer obligation remains attached to the same governed return lane.",
            UpdatedAtUtc: now.AddMinutes(4));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [heatPressureLane, contactObligationLane],
            Consequences: [],
            AftermathPackages: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithCampaignReturnRelationshipReceiptEvidenceOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        CampaignConsequenceReceipt receipt = new(
            ReceiptId: "receipt-1",
            SourceKind: "support_case",
            Summary: "Support case receipt confirms heat pressure remains governed for return.");
        CampaignConsequenceProjection heatVariant = new(
            ConsequenceId: "consequence-1",
            Kind: "heat_pressure_lane",
            Label: "Heat pressure",
            State: "elevated",
            Summary: "",
            EvidenceLines: [],
            Receipts: [receipt],
            UpdatedAtUtc: now.AddMinutes(3));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [],
            Consequences: [heatVariant],
            AftermathPackages: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithSparseRelationshipConsequenceKindsAndLabelsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        CampaignConsequenceProjection consequence = new(
            ConsequenceId: "consequence-1",
            Kind: "",
            Label: "Heat pressure consequence label",
            State: "elevated",
            Summary: "Status shifted during downtime follow-through.",
            EvidenceLines: [],
            Receipts: [],
            UpdatedAtUtc: now.AddMinutes(3));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [],
            Consequences: [consequence],
            AftermathPackages: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithSparseRelationshipConsequenceFalloutLabelOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        CampaignConsequenceProjection consequence = new(
            ConsequenceId: "consequence-1",
            Kind: "",
            Label: "Contact fallout consequence label",
            State: "elevated",
            Summary: "",
            EvidenceLines: [],
            Receipts: [],
            UpdatedAtUtc: now.AddMinutes(3));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [],
            Consequences: [consequence],
            AftermathPackages: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithSparseRelationshipMentionOnlyConsequenceEvidence()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        CampaignConsequenceProjection consequence = new(
            ConsequenceId: "consequence-1",
            Kind: "",
            Label: "",
            State: "steady",
            Summary: "",
            EvidenceLines: ["Contact directory note captured for table reference."],
            Receipts: [],
            UpdatedAtUtc: now.AddMinutes(3));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [],
            Consequences: [consequence],
            AftermathPackages: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithRelationshipConsequenceKindWithoutMutationOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        CampaignConsequenceProjection consequence = new(
            ConsequenceId: "consequence-1",
            Kind: "contact_registry",
            Label: "",
            State: "steady",
            Summary: "",
            EvidenceLines: [],
            Receipts: [],
            UpdatedAtUtc: now.AddMinutes(3));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [],
            Consequences: [consequence],
            AftermathPackages: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithBacklogMentionsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        WorkspaceChangePacketProjection backlogSignal = new(
            PacketId: "packet-backlog-1",
            Kind: "status_note",
            Label: "Campaign backlog review",
            Summary: "Backlog status remains stable while triage work is scheduled.",
            UpdatedAtUtc: now.AddMinutes(3));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-backlog-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [backlogSignal],
            Consequences: [],
            AftermathPackages: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithAuditLogMentionsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        WorkspaceChangePacketProjection auditLogSignal = new(
            PacketId: "packet-audit-log-1",
            Kind: "status_note",
            Label: "Audit log review",
            Summary: "Audit log entries stay stable while governance triage is scheduled.",
            UpdatedAtUtc: now.AddMinutes(4));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-audit-log-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [auditLogSignal],
            Consequences: [],
            AftermathPackages: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithRecapitalizationMentionsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        WorkspaceChangePacketProjection recapitalizationSignal = new(
            PacketId: "packet-recapitalization-1",
            Kind: "status_note",
            Label: "Recapitalization planning note",
            Summary: "Recapitalization planning remains pending for fiscal review.",
            UpdatedAtUtc: now.AddMinutes(4));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-recapitalization-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [recapitalizationSignal],
            Consequences: [],
            AftermathPackages: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithRecapitalizationKindOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        WorkspaceChangePacketProjection recapitalizationSignal = new(
            PacketId: "packet-recapitalization-kind-1",
            Kind: "recapitalization_signal",
            Label: "Fiscal planning signal",
            Summary: "Fiscal planning remains pending for finance review.",
            UpdatedAtUtc: now.AddMinutes(4));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-recapitalization-kind-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [recapitalizationSignal],
            Consequences: [],
            AftermathPackages: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithAfterActionableMentionsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        WorkspaceChangePacketProjection afterActionableSignal = new(
            PacketId: "packet-after-actionable-1",
            Kind: "status_after_actionable_note",
            Label: "After actionable checklist review",
            Summary: "Actionable follow-ups were documented for general table hygiene.",
            UpdatedAtUtc: now.AddMinutes(4));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-after-actionable-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [afterActionableSignal],
            Consequences: [],
            AftermathPackages: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithCampaignReturnSignalLabelsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        WorkspaceChangePacketProjection returnWindow = new(
            PacketId: "packet-1",
            Kind: "campaign_return_window",
            Label: "Return window label",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(2));
        WorkspaceChangePacketProjection contactPressure = new(
            PacketId: "packet-2",
            Kind: "contact_obligation_lane",
            Label: "Fixer obligation label",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(3));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [returnWindow, contactPressure],
            Consequences: [],
            AftermathPackages: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithCampaignReturnCarryForwardLabelOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        NextSessionCarryForwardProjection carryForward = new(
            CarryForwardId: "carry-1",
            Label: "Return lane label",
            Summary: "",
            ReturnSummary: "",
            NextSafeAction: "Reopen from governed return lane.",
            EvidenceLines: [],
            UpdatedAtUtc: now.AddMinutes(2));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [],
            Consequences: [],
            NextSessionCarryForward: carryForward,
            AftermathPackages: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithContinuityOnlyCarryForwardNotes()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        NextSessionCarryForwardProjection carryForward = new(
            CarryForwardId: "carry-continuity-only-1",
            Label: "Continuity board note",
            Summary: "Campaign continuity remains steady while operator planning is pending.",
            ReturnSummary: "Continuity checklist remains unchanged.",
            NextSafeAction: "Review continuity board updates before next planning review.",
            EvidenceLines:
            [
                "Continuity board audit note captured.",
                "No relationship mutation receipt is attached."
            ],
            UpdatedAtUtc: now.AddMinutes(2));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-continuity-only-carry-forward-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [],
            Consequences: [],
            NextSessionCarryForward: carryForward,
            AftermathPackages: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithCampaignReturnCarryForwardEvidenceSignalsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        NextSessionCarryForwardProjection carryForward = new(
            CarryForwardId: "carry-1",
            Label: "",
            Summary: "",
            ReturnSummary: "",
            NextSafeAction: "",
            EvidenceLines:
            [
                "campaign_return_window",
                "contact status changed after downtime"
            ],
            UpdatedAtUtc: now.AddMinutes(2));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [],
            Consequences: [],
            NextSessionCarryForward: carryForward,
            AftermathPackages: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithCampaignReturnSparseSignalKindsAndLabelsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        WorkspaceChangePacketProjection returnWindow = new(
            PacketId: "packet-1",
            Kind: "",
            Label: "Return window label",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(2));
        WorkspaceChangePacketProjection contactPressure = new(
            PacketId: "packet-2",
            Kind: "",
            Label: "Contact pressure label",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(3));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [returnWindow, contactPressure],
            Consequences: [],
            AftermathPackages: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithCampaignReturnSplitRelationshipSignalTokens()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        WorkspaceChangePacketProjection returnWindow = new(
            PacketId: "packet-1",
            Kind: "",
            Label: "Return window label",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(2));
        WorkspaceChangePacketProjection splitRelationship = new(
            PacketId: "packet-2",
            Kind: "",
            Label: "Contact lane label",
            Summary: "Status changed after downtime reconciliation.",
            UpdatedAtUtc: now.AddMinutes(3));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [returnWindow, splitRelationship],
            Consequences: [],
            AftermathPackages: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithCampaignReturnStructuredSplitRelationshipSignalTokens()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        WorkspaceChangePacketProjection returnWindow = new(
            PacketId: "packet-1",
            Kind: "",
            Label: "Return window label",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(2));
        WorkspaceChangePacketProjection splitRelationship = new(
            PacketId: "packet-2",
            Kind: "relationship_window",
            Label: "Contact board label",
            Summary: "Continuity board wording only.",
            UpdatedAtUtc: now.AddMinutes(3));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [returnWindow, splitRelationship],
            Consequences: [],
            AftermathPackages: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithCampaignReturnConsequenceEvidenceStructuredSplitRelationshipSignalTokens()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        WorkspaceChangePacketProjection returnWindow = new(
            PacketId: "packet-1",
            Kind: "",
            Label: "Return window label",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(2));
        CampaignConsequenceProjection consequence = new(
            ConsequenceId: "consequence-1",
            Kind: "continuity_note",
            Label: "Contact board label",
            State: "",
            Summary: "Continuity board wording only.",
            EvidenceLines:
            [
                "relationship_window",
                "contact board label"
            ],
            Receipts: [],
            UpdatedAtUtc: now.AddMinutes(3));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [returnWindow],
            Consequences: [consequence],
            AftermathPackages: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithCampaignReturnKindsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        WorkspaceChangePacketProjection returnWindow = new(
            PacketId: "packet-1",
            Kind: "campaign_return_window",
            Label: "",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(1));
        CampaignConsequenceProjection heatLane = new(
            ConsequenceId: "consequence-1",
            Kind: "heat_pressure_lane",
            Label: "",
            State: "",
            Summary: "",
            EvidenceLines: [],
            Receipts: [],
            UpdatedAtUtc: now.AddMinutes(2));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [returnWindow],
            Consequences: [heatLane],
            AftermathPackages: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithCampaignReturnKindsAndVerboseCarryForward()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        WorkspaceChangePacketProjection returnWindow = new(
            PacketId: "packet-1",
            Kind: "campaign_return_window",
            Label: "",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(1));
        CampaignConsequenceProjection heatLane = new(
            ConsequenceId: "consequence-1",
            Kind: "heat_pressure_lane",
            Label: "",
            State: "elevated",
            Summary: "",
            EvidenceLines: [],
            Receipts: [],
            UpdatedAtUtc: now.AddMinutes(2));
        NextSessionCarryForwardProjection carryForward = new(
            CarryForwardId: "carry-1",
            Label: "Return lane priority",
            Summary: "Carry-forward summary keeps reopen actions staged.",
            ReturnSummary: "Return summary keeps the session handoff governed.",
            NextSafeAction: "Reopen the campaign from the governed return lane.",
            EvidenceLines: [],
            UpdatedAtUtc: now.AddMinutes(3));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [returnWindow],
            Consequences: [heatLane],
            NextSessionCarryForward: carryForward,
            AftermathPackages: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithCampaignReturnKindsAndVerboseDiaryEvidence()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        WorkspaceChangePacketProjection returnWindow = new(
            PacketId: "packet-1",
            Kind: "campaign_return_window",
            Label: "",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(1));
        CampaignConsequenceProjection heatLane = new(
            ConsequenceId: "consequence-1",
            Kind: "heat_pressure_lane",
            Label: "",
            State: "",
            Summary: "",
            EvidenceLines: [],
            Receipts: [],
            UpdatedAtUtc: now.AddMinutes(2));
        PublicationSafeProjection recapA = new(
            ProjectionId: "recap-1",
            Kind: "session_recap",
            Label: "Session recap lane A",
            Summary: "Session recap evidence line A remains verbose while return packets hydrate.");
        PublicationSafeProjection recapB = new(
            ProjectionId: "recap-2",
            Kind: "session_recap",
            Label: "Session recap lane B",
            Summary: "Session recap evidence line B remains verbose while return packets hydrate.");
        PublicationSafeProjection recapC = new(
            ProjectionId: "recap-3",
            Kind: "session_recap",
            Label: "Session recap lane C",
            Summary: "Session recap evidence line C remains verbose while return packets hydrate.");

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [recapA, recapB, recapC],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [returnWindow],
            Consequences: [heatLane],
            AftermathPackages: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithCampaignReturnRecapKindsOnly()
    {
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        PublicationSafeProjection recap = new(
            ProjectionId: "recap-1",
            Kind: "session_recap",
            Label: "",
            Summary: "");

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [recap],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [],
            Consequences: [],
            AftermathPackages: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithCampaignReturnRecapKindOnly(string kind)
    {
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        PublicationSafeProjection recap = new(
            ProjectionId: "recap-1",
            Kind: kind,
            Label: "",
            Summary: "");

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [recap],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [],
            Consequences: [],
            AftermathPackages: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithCampaignReturnRecapLabelOnly()
    {
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        PublicationSafeProjection recap = new(
            ProjectionId: "recap-1",
            Kind: "",
            Label: "Session diary recap label",
            Summary: "");

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [recap],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [],
            Consequences: [],
            AftermathPackages: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithTravelPrefetchChangeSignalsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        WorkspaceChangePacketProjection prefetchChange = new(
            PacketId: "packet-1",
            Kind: "travel_prefetch",
            Label: "Travel prefetch signal",
            Summary: "Travel prefetch change packet staged bounded offline inventory for the next return loop.",
            UpdatedAtUtc: now.AddMinutes(4));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [prefetchChange],
            Consequences: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithTravelPrefetchSignalLabelsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        WorkspaceChangePacketProjection prefetchChange = new(
            PacketId: "packet-1",
            Kind: "travel_prefetch",
            Label: "Travel prefetch label",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(4));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [prefetchChange],
            Consequences: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithTravelPrefetchKindsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        WorkspaceChangePacketProjection prefetchChange = new(
            PacketId: "packet-1",
            Kind: "travel_prefetch",
            Label: "",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(4));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [prefetchChange],
            Consequences: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithTravelPrefetchSparseSignalKindsAndLabelsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        WorkspaceChangePacketProjection prefetchChange = new(
            PacketId: "packet-1",
            Kind: "",
            Label: "Travel prefetch label",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(4));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [prefetchChange],
            Consequences: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithTravelPrefetchSparseSignalKindsAndSplitTokens()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        WorkspaceChangePacketProjection prefetchChange = new(
            PacketId: "packet-1",
            Kind: "",
            Label: "Travel staging label",
            Summary: "Prefetch ready for travel cache.",
            UpdatedAtUtc: now.AddMinutes(4));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [prefetchChange],
            Consequences: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithTravelPrefetchKindsAndVerboseReceiptEvidence()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        WorkspaceChangePacketProjection prefetchChange = new(
            PacketId: "packet-1",
            Kind: "travel_prefetch",
            Label: "",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(8));

        TravelPrefetchReceiptProjection receiptOne = new(
            ReceiptId: "prefetch-1",
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            InstallationId: "install-1",
            DeviceRole: "travel_cache",
            Platform: "ios",
            HeadId: "mobile",
            Channel: "preview",
            PrefetchSummary: "Verbose prefetch summary line one.",
            InventoryLines: [],
            Boundaries: [],
            InitiatedByUserId: "gm-1",
            StagedAtUtc: now.AddMinutes(4));
        TravelPrefetchReceiptProjection receiptTwo = new(
            ReceiptId: "prefetch-2",
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            InstallationId: "install-2",
            DeviceRole: "travel_cache",
            Platform: "android",
            HeadId: "mobile",
            Channel: "preview",
            PrefetchSummary: "Verbose prefetch summary line two.",
            InventoryLines: [],
            Boundaries: [],
            InitiatedByUserId: "gm-1",
            StagedAtUtc: now.AddMinutes(5));
        TravelPrefetchReceiptProjection receiptThree = new(
            ReceiptId: "prefetch-3",
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            InstallationId: "install-3",
            DeviceRole: "travel_cache",
            Platform: "windows",
            HeadId: "desktop",
            Channel: "stable",
            PrefetchSummary: "Verbose prefetch summary line three.",
            InventoryLines: [],
            Boundaries: [],
            InitiatedByUserId: "gm-1",
            StagedAtUtc: now.AddMinutes(6));
        TravelPrefetchReceiptProjection receiptFour = new(
            ReceiptId: "prefetch-4",
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            InstallationId: "install-4",
            DeviceRole: "travel_cache",
            Platform: "linux",
            HeadId: "desktop",
            Channel: "stable",
            PrefetchSummary: "Verbose prefetch summary line four.",
            InventoryLines: [],
            Boundaries: [],
            InitiatedByUserId: "gm-1",
            StagedAtUtc: now.AddMinutes(7));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [prefetchChange],
            Consequences: [],
            TravelPrefetches: [receiptOne, receiptTwo, receiptThree, receiptFour]);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithRunPressureSignalsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        ObjectiveProjection objective = new(
            ObjectiveId: "objective-1",
            Title: "Hostile extraction team",
            Status: "open",
            Pressure: "high",
            Summary: "An extraction team remains active and pushes immediate opposition risk.",
            UpdatedAtUtc: now.AddMinutes(2));

        SceneProjection scene = new(
            SceneId: "scene-1",
            RunId: "run-1",
            Title: "Dockyard checkpoint",
            Revision: "r3",
            Status: "active",
            Summary: "Opposition remains active around the dockyard perimeter.",
            UpdatedAtUtc: now.AddMinutes(3));

        RunProjection run = new(
            RunId: "run-1",
            CampaignId: "campaign-a",
            Title: "Dockyard pressure test",
            Status: "active",
            Summary: "Current run remains under hostile pressure.",
            ActiveSceneId: "scene-1",
            Objectives: [objective],
            Scenes: [scene],
            LatestContinuity: null,
            CreatedAtUtc: now.AddDays(-1),
            UpdatedAtUtc: now.AddMinutes(4));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [run],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [],
            Consequences: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithBenignRunSignalsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        ObjectiveProjection objective = new(
            ObjectiveId: "objective-1",
            Title: "Inventory refresh checklist",
            Status: "open",
            Pressure: "low",
            Summary: "The table inventory checklist remains open for bookkeeping.",
            UpdatedAtUtc: now.AddMinutes(2));

        SceneProjection scene = new(
            SceneId: "scene-1",
            RunId: "run-1",
            Title: "Backroom inventory desk",
            Revision: "r1",
            Status: "active",
            Summary: "Backroom inventory reconciliation is still in progress.",
            UpdatedAtUtc: now.AddMinutes(3));

        RunProjection run = new(
            RunId: "run-1",
            CampaignId: "campaign-a",
            Title: "Backroom ledger pass",
            Status: "active",
            Summary: "Current run remains focused on bookkeeping updates.",
            ActiveSceneId: "scene-1",
            Objectives: [objective],
            Scenes: [scene],
            LatestContinuity: null,
            CreatedAtUtc: now.AddDays(-1),
            UpdatedAtUtc: now.AddMinutes(4));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [run],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [],
            Consequences: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithBenignSceneSummaryOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        SceneProjection scene = new(
            SceneId: "scene-1",
            RunId: "run-1",
            Title: "Backroom inventory desk",
            Revision: "r1",
            Status: "active",
            Summary: "Backroom inventory reconciliation is still in progress.",
            UpdatedAtUtc: now.AddMinutes(3));

        RunProjection run = new(
            RunId: "run-1",
            CampaignId: "campaign-a",
            Title: "Backroom ledger pass",
            Status: "active",
            Summary: "Current run remains focused on bookkeeping updates.",
            ActiveSceneId: "scene-1",
            Objectives: [],
            Scenes: [scene],
            LatestContinuity: null,
            CreatedAtUtc: now.AddDays(-1),
            UpdatedAtUtc: now.AddMinutes(4));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [run],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [],
            Consequences: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithSceneSignalLabelsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        ObjectiveProjection objective = new(
            ObjectiveId: "objective-1",
            Title: "Hostile extraction team label",
            Status: "open",
            Pressure: "high",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(2));

        SceneProjection scene = new(
            SceneId: "scene-1",
            RunId: "run-1",
            Title: "Dockyard checkpoint label",
            Revision: "r3",
            Status: "active",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(3));

        RunProjection run = new(
            RunId: "run-1",
            CampaignId: "campaign-a",
            Title: "Dockyard pressure test",
            Status: "active",
            Summary: "",
            ActiveSceneId: "scene-1",
            Objectives: [objective],
            Scenes: [scene],
            LatestContinuity: null,
            CreatedAtUtc: now.AddDays(-1),
            UpdatedAtUtc: now.AddMinutes(4));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [run],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [],
            Consequences: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithSparseRunAndSceneTitles()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        SceneProjection scene = new(
            SceneId: "scene-1",
            RunId: "run-1",
            Title: "",
            Revision: "r3",
            Status: "active",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(3));

        RunProjection run = new(
            RunId: "run-1",
            CampaignId: "campaign-a",
            Title: "",
            Status: "active",
            Summary: "",
            ActiveSceneId: "scene-1",
            Objectives: [],
            Scenes: [scene],
            LatestContinuity: null,
            CreatedAtUtc: now.AddDays(-1),
            UpdatedAtUtc: now.AddMinutes(4));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [run],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [],
            Consequences: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithEventControlSignalVariants()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        WorkspaceChangePacketProjection prepLaunchVariant = new(
            PacketId: "packet-1",
            Kind: "prep_packet_launch",
            Label: "Prep launch variant",
            Summary: "Prep launch variant packet remains attached to event controls.",
            UpdatedAtUtc: now.AddMinutes(1));
        WorkspaceChangePacketProjection travelPrefetchVariant = new(
            PacketId: "packet-2",
            Kind: "travel_prefetch_request",
            Label: "Travel prefetch variant",
            Summary: "Travel prefetch variant packet remains attached to event controls.",
            UpdatedAtUtc: now.AddMinutes(2));
        WorkspaceChangePacketProjection rosterVariant = new(
            PacketId: "packet-3",
            Kind: "crew_handoff",
            Label: "Roster movement variant",
            Summary: "Crew handoff variant packet remains attached to season operations.",
            UpdatedAtUtc: now.AddMinutes(3));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [prepLaunchVariant, travelPrefetchVariant, rosterVariant],
            Consequences: [],
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithEventControlRelationshipSignalsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        WorkspaceChangePacketProjection relationshipChange = new(
            PacketId: "packet-1",
            Kind: "heat_update",
            Label: "Heat relationship update",
            Summary: "Relationship update keeps heat posture attached to event controls before consequence receipts land.",
            UpdatedAtUtc: now.AddMinutes(2));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [relationshipChange],
            Consequences: [],
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithEventControlRelationshipConsequenceVariantsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        CampaignConsequenceProjection heatVariant = new(
            ConsequenceId: "consequence-1",
            Kind: "heat_pressure_lane",
            Label: "Heat pressure",
            State: "elevated",
            Summary: "Heat pressure remains attached to event-control governance.",
            EvidenceLines: ["Heat pressure review captured for season controls."],
            Receipts: [],
            UpdatedAtUtc: now.AddMinutes(3));
        CampaignConsequenceProjection factionVariant = new(
            ConsequenceId: "consequence-2",
            Kind: "faction_pressure_lane",
            Label: "Faction pressure",
            State: "contested",
            Summary: "Faction pressure remains attached to event-control governance.",
            EvidenceLines: ["Faction pressure review captured for season controls."],
            Receipts: [],
            UpdatedAtUtc: now.AddMinutes(4));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [],
            Consequences: [heatVariant, factionVariant],
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithEventControlRelationshipSignalVariantsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        WorkspaceChangePacketProjection heatPressureLane = new(
            PacketId: "packet-1",
            Kind: "heat_pressure_lane",
            Label: "Heat pressure lane",
            Summary: "Heat pressure remains attached to event controls while consequence receipts catch up.",
            UpdatedAtUtc: now.AddMinutes(2));
        WorkspaceChangePacketProjection contactObligationLane = new(
            PacketId: "packet-2",
            Kind: "contact_obligation_lane",
            Label: "Fixer obligation lane",
            Summary: "Fixer obligation remains attached to event controls on the same governed lane.",
            UpdatedAtUtc: now.AddMinutes(3));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [heatPressureLane, contactObligationLane],
            Consequences: [],
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithEventControlRelationshipReceiptEvidenceOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        CampaignConsequenceReceipt receipt = new(
            ReceiptId: "receipt-1",
            SourceKind: "support_case",
            Summary: "Support case receipt confirms heat pressure remains attached to event control.");
        CampaignConsequenceProjection heatVariant = new(
            ConsequenceId: "consequence-1",
            Kind: "heat_pressure_lane",
            Label: "Heat pressure",
            State: "elevated",
            Summary: "",
            EvidenceLines: [],
            Receipts: [receipt],
            UpdatedAtUtc: now.AddMinutes(2));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [],
            Consequences: [heatVariant],
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithEventControlSignalLabelsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        WorkspaceChangePacketProjection seasonOperation = new(
            PacketId: "packet-1",
            Kind: "season_operation_checkpoint",
            Label: "Season operation label",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(2));
        WorkspaceChangePacketProjection relationshipPressure = new(
            PacketId: "packet-2",
            Kind: "contact_pressure_lane",
            Label: "Contact pressure label",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(3));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [seasonOperation, relationshipPressure],
            Consequences: [],
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithEventControlSignalKindsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        WorkspaceChangePacketProjection seasonOperation = new(
            PacketId: "packet-1",
            Kind: "season_operation_checkpoint",
            Label: "",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(2));
        WorkspaceChangePacketProjection eventWindowShift = new(
            PacketId: "packet-2",
            Kind: "event_window_shift",
            Label: "",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(3));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [seasonOperation, eventWindowShift],
            Consequences: [],
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithEventControlSparseSignalKindsAndLabelsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        WorkspaceChangePacketProjection seasonOperation = new(
            PacketId: "packet-1",
            Kind: "",
            Label: "Season operation label",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(2));
        WorkspaceChangePacketProjection relationshipPressure = new(
            PacketId: "packet-2",
            Kind: "",
            Label: "Contact pressure label",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(3));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [seasonOperation, relationshipPressure],
            Consequences: [],
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithEventControlSplitRelationshipSignalTokens()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        WorkspaceChangePacketProjection seasonOperation = new(
            PacketId: "packet-1",
            Kind: "",
            Label: "Season operation label",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(2));
        WorkspaceChangePacketProjection splitRelationship = new(
            PacketId: "packet-2",
            Kind: "",
            Label: "Contact lane label",
            Summary: "Status changed after organizer checkpoint reconciliation.",
            UpdatedAtUtc: now.AddMinutes(3));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [seasonOperation, splitRelationship],
            Consequences: [],
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithEventControlStructuredSplitRelationshipSignalTokens()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        WorkspaceChangePacketProjection seasonOperation = new(
            PacketId: "packet-1",
            Kind: "",
            Label: "Season operation label",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(2));
        WorkspaceChangePacketProjection splitRelationship = new(
            PacketId: "packet-2",
            Kind: "relationship_window",
            Label: "Contact board label",
            Summary: "Continuity board wording only.",
            UpdatedAtUtc: now.AddMinutes(3));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [seasonOperation, splitRelationship],
            Consequences: [],
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithEventControlConsequenceEvidenceStructuredSplitRelationshipSignalTokens()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        WorkspaceChangePacketProjection seasonOperation = new(
            PacketId: "packet-1",
            Kind: "",
            Label: "Season operation label",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(2));
        CampaignConsequenceProjection consequence = new(
            ConsequenceId: "consequence-1",
            Kind: "continuity_note",
            Label: "Contact board label",
            State: "",
            Summary: "Continuity board wording only.",
            EvidenceLines:
            [
                "relationship_window",
                "contact board label"
            ],
            Receipts: [],
            UpdatedAtUtc: now.AddMinutes(3));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [seasonOperation],
            Consequences: [consequence],
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithEventControlRelationshipOnlySplitSignalTokens()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        WorkspaceChangePacketProjection splitRelationship = new(
            PacketId: "packet-1",
            Kind: "",
            Label: "Contact lane label",
            Summary: "Status changed after downtime.",
            UpdatedAtUtc: now.AddMinutes(3));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [splitRelationship],
            Consequences: [],
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithEventControlCarryForwardLabelOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        NextSessionCarryForwardProjection carryForward = new(
            CarryForwardId: "carry-1",
            Label: "Event control label",
            Summary: "",
            ReturnSummary: "",
            NextSafeAction: "Open season controls before next launch.",
            EvidenceLines: [],
            UpdatedAtUtc: now.AddMinutes(2));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [],
            Consequences: [],
            NextSessionCarryForward: carryForward,
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithEventControlConsequenceKindsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        CampaignConsequenceProjection heatVariant = new(
            ConsequenceId: "consequence-1",
            Kind: "heat_pressure_lane",
            Label: "",
            State: "elevated",
            Summary: "Heat pressure stays attached to event controls.",
            EvidenceLines: [],
            Receipts: [],
            UpdatedAtUtc: now.AddMinutes(2));
        CampaignConsequenceProjection factionVariant = new(
            ConsequenceId: "consequence-2",
            Kind: "faction_status_window",
            Label: "",
            State: "active",
            Summary: "Faction pressure stays attached to event controls.",
            EvidenceLines: [],
            Receipts: [],
            UpdatedAtUtc: now.AddMinutes(3));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [],
            Consequences: [heatVariant, factionVariant],
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithNonEventCarryForwardOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        NextSessionCarryForwardProjection carryForward = new(
            CarryForwardId: "carry-1",
            Label: "Budget review note",
            Summary: "Audit receipt reconciliation is pending for publication notes.",
            ReturnSummary: "Document refresh queue remains open for operator follow-through.",
            NextSafeAction: "Review publication checklist before posting the update.",
            EvidenceLines: [],
            UpdatedAtUtc: now.AddMinutes(2));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [],
            Consequences: [],
            NextSessionCarryForward: carryForward,
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithEventControlCarryForwardWindowOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        NextSessionCarryForwardProjection carryForward = new(
            CarryForwardId: "carry-1",
            Label: "Return window note",
            Summary: "Window remains open for continuity review.",
            ReturnSummary: "Shared return window stays visible to the table.",
            NextSafeAction: "Review the return lane window before reopening play.",
            EvidenceLines: [],
            UpdatedAtUtc: now.AddMinutes(2));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [],
            Consequences: [],
            NextSessionCarryForward: carryForward,
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithEventControlContinuitySignalsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        WorkspaceChangePacketProjection continuitySignal = new(
            PacketId: "packet-1",
            Kind: "next_session_carry_forward",
            Label: "Continuity carry-forward signal",
            Summary: "Continuity handoff remains attached to the return lane.",
            UpdatedAtUtc: now.AddMinutes(2));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [continuitySignal],
            Consequences: [],
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithEventControlAftermathSignalsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        WorkspaceChangePacketProjection aftermathSignal = new(
            PacketId: "packet-1",
            Kind: "downtime_brief",
            Label: "Downtime brief signal",
            Summary: "Aftermath remains visible for return-loop continuity.",
            UpdatedAtUtc: now.AddMinutes(2));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [aftermathSignal],
            Consequences: [],
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithCrewMentionsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        WorkspaceChangePacketProjection crewMentionSignal = new(
            PacketId: "packet-crew-1",
            Kind: "continuity_update",
            Label: "Crew morale pulse",
            Summary: "Crew morale remains stable after downtime review.",
            UpdatedAtUtc: now.AddMinutes(3));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-crew-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [crewMentionSignal],
            Consequences: [],
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithCrewRemoveMentionsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        WorkspaceChangePacketProjection crewRemoveSignal = new(
            PacketId: "packet-crew-remove-1",
            Kind: "continuity_update",
            Label: "Crew morale note",
            Summary: "Crew morale review will remove stale recap clutter after downtime.",
            UpdatedAtUtc: now.AddMinutes(3));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-crew-remove-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [crewRemoveSignal],
            Consequences: [],
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithCrewBenchmarkMentionsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        WorkspaceChangePacketProjection crewBenchmarkSignal = new(
            PacketId: "packet-crew-benchmark-1",
            Kind: "continuity_update",
            Label: "Crew benchmark review",
            Summary: "Crew benchmark remains stable across continuity review.",
            UpdatedAtUtc: now.AddMinutes(3));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-crew-benchmark-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [crewBenchmarkSignal],
            Consequences: [],
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithCrewAssignableMentionsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        WorkspaceChangePacketProjection crewAssignableSignal = new(
            PacketId: "packet-crew-assignable-1",
            Kind: "continuity_update",
            Label: "Crew assignable checklist",
            Summary: "Crew assignable readiness remains a continuity checklist for next-session planning.",
            UpdatedAtUtc: now.AddMinutes(3));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-crew-assignable-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [crewAssignableSignal],
            Consequences: [],
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithCrewReturnLaneMentionsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        WorkspaceChangePacketProjection crewReturnSignal = new(
            PacketId: "packet-crew-return-1",
            Kind: "continuity_update",
            Label: "Crew return lane note",
            Summary: "Crew return window remains governed for continuity follow-through.",
            UpdatedAtUtc: now.AddMinutes(3));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-crew-return-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [crewReturnSignal],
            Consequences: [],
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithRosterReturnableMentionsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        WorkspaceChangePacketProjection rosterReturnableSignal = new(
            PacketId: "packet-roster-returnable-1",
            Kind: "continuity_update",
            Label: "Roster returnable checklist",
            Summary: "Roster returnable notes remain continuity-only and do not imply roster actions.",
            UpdatedAtUtc: now.AddMinutes(3));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-roster-returnable-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [rosterReturnableSignal],
            Consequences: [],
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithFactionInterstateMentionsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        WorkspaceChangePacketProjection interstateSignal = new(
            PacketId: "packet-interstate-1",
            Kind: "routing_note",
            Label: "Faction interstate route note",
            Summary: "Faction interstate routing remains steady for continuity follow-through.",
            UpdatedAtUtc: now.AddMinutes(4));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-interstate-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [interstateSignal],
            Consequences: [],
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithCooperationMentionsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        WorkspaceChangePacketProjection cooperationSignal = new(
            PacketId: "packet-cooperation-1",
            Kind: "continuity_update",
            Label: "Community cooperation pulse",
            Summary: "Cooperation remains stable for continuity follow-through.",
            UpdatedAtUtc: now.AddMinutes(3));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-cooperation-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [cooperationSignal],
            Consequences: [],
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithPreparationRelaunchMentionsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        WorkspaceChangePacketProjection relaunchSignal = new(
            PacketId: "packet-preparation-relaunch-1",
            Kind: "continuity_update",
            Label: "Campaign preparation relaunch note",
            Summary: "Preparation relaunch planning remains continuity-only with no governed dispatch receipt.",
            UpdatedAtUtc: now.AddMinutes(3));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-preparation-relaunch-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [relaunchSignal],
            Consequences: [],
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithTraveloguePrefetchingMentionsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        WorkspaceChangePacketProjection travelogueSignal = new(
            PacketId: "packet-travelogue-prefetching-1",
            Kind: "continuity_update",
            Label: "Travelogue prefetching note",
            Summary: "Travelogue prefetching commentary remains continuity-only.",
            UpdatedAtUtc: now.AddMinutes(4));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-travelogue-prefetching-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [travelogueSignal],
            Consequences: [],
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithContactlessStatusMentionsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        WorkspaceChangePacketProjection contactlessSignal = new(
            PacketId: "packet-contactless-1",
            Kind: "continuity_update",
            Label: "Contactless kiosk status",
            Summary: "Contactless queue status remains stable during recap.",
            UpdatedAtUtc: now.AddMinutes(4));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-contactless-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [contactlessSignal],
            Consequences: [],
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithContactStatusMentionsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        WorkspaceChangePacketProjection contactStatusSignal = new(
            PacketId: "packet-contact-status-1",
            Kind: "status_note",
            Label: "Contact status board",
            Summary: "Contact status board remains continuity-only before mutation receipts are logged.",
            UpdatedAtUtc: now.AddMinutes(4));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-contact-status-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [contactStatusSignal],
            Consequences: [],
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithContactStateMentionsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        WorkspaceChangePacketProjection contactStateSignal = new(
            PacketId: "packet-contact-state-1",
            Kind: "status_note",
            Label: "Contact state board",
            Summary: "Contact state board remains continuity-only before mutation receipts are logged.",
            UpdatedAtUtc: now.AddMinutes(4));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-contact-state-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [contactStateSignal],
            Consequences: [],
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithTravelPrefetchableMentionsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        WorkspaceChangePacketProjection prefetchableSignal = new(
            PacketId: "packet-travel-prefetchable-1",
            Kind: "status_note",
            Label: "Travel prefetchable checklist",
            Summary: "Checklist language remains continuity-only for the return board.",
            UpdatedAtUtc: now.AddMinutes(4));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-travel-prefetchable-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [prefetchableSignal],
            Consequences: [],
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithTravelPrefetchableCarryForwardMentionsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        NextSessionCarryForwardProjection carryForward = new(
            CarryForwardId: "carry-travel-prefetchable-1",
            Label: "Travel prefetchable checklist",
            Summary: "Checklist language remains continuity-only for the return board.",
            ReturnSummary: "Return lane note remains governed.",
            NextSafeAction: "Review checklist posture before publication.",
            EvidenceLines: [],
            UpdatedAtUtc: now.AddMinutes(4));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-travel-prefetchable-carry-forward-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [],
            Consequences: [],
            NextSessionCarryForward: carryForward,
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithContactWindowMentionsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        WorkspaceChangePacketProjection contactWindowSignal = new(
            PacketId: "packet-contact-window-1",
            Kind: "status_note",
            Label: "Contact window board",
            Summary: "Contact window board remains continuity-only before mutation receipts are logged.",
            UpdatedAtUtc: now.AddMinutes(4));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-contact-window-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [contactWindowSignal],
            Consequences: [],
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithContactLaneMentionsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        WorkspaceChangePacketProjection contactLaneSignal = new(
            PacketId: "packet-contact-lane-1",
            Kind: "status_note",
            Label: "Contact lane board",
            Summary: "Contact lane board remains continuity-only before mutation receipts are logged.",
            UpdatedAtUtc: now.AddMinutes(4));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-contact-lane-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [contactLaneSignal],
            Consequences: [],
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithContactCooldownMentionsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        WorkspaceChangePacketProjection contactCooldownSignal = new(
            PacketId: "packet-contact-cooldown-1",
            Kind: "status_note",
            Label: "Contact cooldown board",
            Summary: "Contact cooldown board remains continuity-only before mutation receipts are logged.",
            UpdatedAtUtc: now.AddMinutes(4));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-contact-cooldown-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [contactCooldownSignal],
            Consequences: [],
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithContactCoolingMentionsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        WorkspaceChangePacketProjection contactCoolingSignal = new(
            PacketId: "packet-contact-cooling-1",
            Kind: "status_note",
            Label: "Contact cooling board",
            Summary: "Contact cooling board remains continuity-only before mutation receipts are logged.",
            UpdatedAtUtc: now.AddMinutes(4));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-contact-cooling-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [contactCoolingSignal],
            Consequences: [],
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithPrepLaunchableMentionsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        WorkspaceChangePacketProjection launchableSignal = new(
            PacketId: "packet-prep-launchable-1",
            Kind: "status_note",
            Label: "Prep launchable checklist",
            Summary: "Checklist language remains continuity-only for governance prep.",
            UpdatedAtUtc: now.AddMinutes(4));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-prep-launchable-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [launchableSignal],
            Consequences: [],
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithContactDropboxMentionsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        WorkspaceChangePacketProjection dropboxSignal = new(
            PacketId: "packet-contact-dropbox-1",
            Kind: "continuity_note",
            Label: "Contact dropbox mirror",
            Summary: "Contact directory mirror stays synced for continuity notes.",
            UpdatedAtUtc: now.AddMinutes(4));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-contact-dropbox-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [dropboxSignal],
            Consequences: [],
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithContactUpdateableMentionsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        WorkspaceChangePacketProjection updateableSignal = new(
            PacketId: "packet-contact-updateable-1",
            Kind: "continuity_note",
            Label: "Contact updateable template",
            Summary: "Template policy remains stable while governance review is pending.",
            UpdatedAtUtc: now.AddMinutes(4));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-contact-updateable-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [updateableSignal],
            Consequences: [],
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithContactEscalatorMentionsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        WorkspaceChangePacketProjection escalatorSignal = new(
            PacketId: "packet-contact-escalator-1",
            Kind: "continuity_note",
            Label: "Contact escalator policy",
            Summary: "Escalator routing notes stay continuity-only for operator review.",
            UpdatedAtUtc: now.AddMinutes(4));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-contact-escalator-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [escalatorSignal],
            Consequences: [],
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithNonThreateningMentionsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        WorkspaceChangePacketProjection nonThreateningSignal = new(
            PacketId: "packet-nonthreatening-1",
            Kind: "continuity_update",
            Label: "Nonthreatening continuity pulse",
            Summary: "Table posture remains nonthreatening during continuity review.",
            UpdatedAtUtc: now.AddMinutes(4));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-nonthreatening-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [nonThreateningSignal],
            Consequences: [],
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithRosterEventCarryForwardOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        NextSessionCarryForwardProjection carryForward = new(
            CarryForwardId: "carry-1",
            Label: "Roster return carry-forward",
            Summary: "",
            ReturnSummary: "Crew assignment posture stays attached to one governed lane.",
            NextSafeAction: "Resolve roster assignment before next event launch.",
            EvidenceLines: [],
            UpdatedAtUtc: now.AddMinutes(2));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [],
            Consequences: [],
            NextSessionCarryForward: carryForward,
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithRosterCarryForwardEvidenceSignalsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        NextSessionCarryForwardProjection carryForward = new(
            CarryForwardId: "carry-1",
            Label: "Operator ledger note",
            Summary: "Reconcile queue receipts before publishing.",
            ReturnSummary: "Campaign return handoff remains tracked.",
            NextSafeAction: "Review operator checklist.",
            EvidenceLines: ["Roster assignment moved Ghostline into season operations lane."],
            UpdatedAtUtc: now.AddMinutes(2));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [],
            Consequences: [],
            NextSessionCarryForward: carryForward,
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithEventControlCarryForwardEvidenceSignalsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        NextSessionCarryForwardProjection carryForward = new(
            CarryForwardId: "carry-1",
            Label: "Operator ledger note",
            Summary: "Reconcile queue receipts before publishing.",
            ReturnSummary: "Campaign return handoff remains tracked.",
            NextSafeAction: "Review operator checklist.",
            EvidenceLines: ["Opposition window remains active while event controls are reopened."],
            UpdatedAtUtc: now.AddMinutes(2));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [],
            Consequences: [],
            NextSessionCarryForward: carryForward,
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithEventControlCarryForwardRelationshipSignalsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        NextSessionCarryForwardProjection carryForward = new(
            CarryForwardId: "carry-1",
            Label: "Relationship lane carry-forward",
            Summary: "Contact pressure update remains pending.",
            ReturnSummary: "Heat relationship lane remains on return follow-through.",
            NextSafeAction: "Review contact lane update before table reopen.",
            EvidenceLines: ["Contact relationship lane change remains pending."],
            UpdatedAtUtc: now.AddMinutes(2));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [],
            Consequences: [],
            NextSessionCarryForward: carryForward,
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithAftermathCarryForwardSignalsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        NextSessionCarryForwardProjection carryForward = new(
            CarryForwardId: "carry-1",
            Label: "Aftermath lane carry-forward",
            Summary: "",
            ReturnSummary: "Downtime brief remains attached to the return lane.",
            NextSafeAction: "Review aftermath board before table return.",
            EvidenceLines: [],
            UpdatedAtUtc: now.AddMinutes(2));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [],
            Consequences: [],
            NextSessionCarryForward: carryForward,
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithAftermathCarryForwardEvidenceSignalsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        NextSessionCarryForwardProjection carryForward = new(
            CarryForwardId: "carry-1",
            Label: "Operator ledger note",
            Summary: "Reconcile queue receipts before publishing.",
            ReturnSummary: "Campaign return handoff remains tracked.",
            NextSafeAction: "Review operator checklist.",
            EvidenceLines: ["Aftermath downtime brief remains active while return lane is reopened."],
            UpdatedAtUtc: now.AddMinutes(2));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [],
            Consequences: [],
            NextSessionCarryForward: carryForward,
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithAftermathOutBriefCarryForwardSplitTokensOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        NextSessionCarryForwardProjection carryForward = new(
            CarryForwardId: "carry-out-brief-1",
            Label: "Out brief carry-forward",
            Summary: "",
            ReturnSummary: "Out-briefings stay attached to the governed return lane.",
            NextSafeAction: "Review recap board before table return.",
            EvidenceLines: [],
            UpdatedAtUtc: now.AddMinutes(2));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [],
            Consequences: [],
            NextSessionCarryForward: carryForward,
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithAftermathHotWashCarryForwardEvidenceSplitTokensOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        NextSessionCarryForwardProjection carryForward = new(
            CarryForwardId: "carry-hot-wash-1",
            Label: "Operator queue note",
            Summary: "Release checklist remains pending.",
            ReturnSummary: "Campaign return handoff remains tracked.",
            NextSafeAction: "Review operator checklist.",
            EvidenceLines: ["Hot-wash fallout remains pinned for recap before table reopen."],
            UpdatedAtUtc: now.AddMinutes(2));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [],
            Consequences: [],
            NextSessionCarryForward: carryForward,
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithAftermathPostMortemCarryForwardSplitTokensOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        NextSessionCarryForwardProjection carryForward = new(
            CarryForwardId: "carry-post-mortem-1",
            Label: "Post mortem carry-forward",
            Summary: "",
            ReturnSummary: "Post-mortems stay attached to the governed return lane.",
            NextSafeAction: "Review recap board before table return.",
            EvidenceLines: [],
            UpdatedAtUtc: now.AddMinutes(2));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [],
            Consequences: [],
            NextSessionCarryForward: carryForward,
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithAftermathPostSessionAndPostRunCarryForwardEvidenceSplitTokensOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        NextSessionCarryForwardProjection carryForward = new(
            CarryForwardId: "carry-post-session-run-1",
            Label: "Operator queue note",
            Summary: "Release checklist remains pending.",
            ReturnSummary: "Campaign return handoff remains tracked.",
            NextSafeAction: "Review operator checklist.",
            EvidenceLines:
            [
                "Post-session fallout remains pinned for recap before table reopen.",
                "Post run follow-through remains governed until return is confirmed."
            ],
            UpdatedAtUtc: now.AddMinutes(2));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [],
            Consequences: [],
            NextSessionCarryForward: carryForward,
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithAftermathSignalAndUnrelatedCarryForwardTimestampSkew()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        WorkspaceChangePacketProjection aftermathSignal = new(
            PacketId: "packet-aftermath-1",
            Kind: "aftermath",
            Label: "Aftermath lane update",
            Summary: "Aftermath lane remains governed while recap packages hydrate.",
            UpdatedAtUtc: now.AddMinutes(1));
        NextSessionCarryForwardProjection carryForward = new(
            CarryForwardId: "carry-unrelated-1",
            Label: "Operator queue note",
            Summary: "Publish checklist reconciliation is still pending.",
            ReturnSummary: "Workspace governance note remains open.",
            NextSafeAction: "Review operator queue before docs refresh.",
            EvidenceLines: ["Queue evidence remains pending reconciliation."],
            UpdatedAtUtc: now.AddMinutes(9));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-aftermath-updated-at-skew-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [aftermathSignal],
            Consequences: [],
            NextSessionCarryForward: carryForward,
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithEventControlSignalAndUnrelatedCarryForwardTimestampSkew()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        WorkspaceChangePacketProjection eventControlSignal = new(
            PacketId: "packet-event-control-1",
            Kind: "event_control",
            Label: "Event control update",
            Summary: "Season control remains active on the governed lane.",
            UpdatedAtUtc: now.AddMinutes(1));
        NextSessionCarryForwardProjection carryForward = new(
            CarryForwardId: "carry-unrelated-2",
            Label: "Operator queue note",
            Summary: "Publication checklist reconciliation is still pending.",
            ReturnSummary: "Workspace governance note remains open.",
            NextSafeAction: "Review operator queue before docs refresh.",
            EvidenceLines: ["Queue evidence remains pending reconciliation."],
            UpdatedAtUtc: now.AddMinutes(9));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-event-control-updated-at-skew-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [eventControlSignal],
            Consequences: [],
            NextSessionCarryForward: carryForward,
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithContinuitySignalAndUnrelatedCarryForwardTimestampSkew()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        WorkspaceChangePacketProjection continuitySignal = new(
            PacketId: "packet-continuity-1",
            Kind: "continuity",
            Label: "Continuity lane update",
            Summary: "Continuity lane remains governed for the next session handoff.",
            UpdatedAtUtc: now.AddMinutes(1));
        NextSessionCarryForwardProjection carryForward = new(
            CarryForwardId: "carry-unrelated-continuity-1",
            Label: "Operator queue note",
            Summary: "Publication checklist reconciliation is still pending.",
            ReturnSummary: "Workspace governance note remains open.",
            NextSafeAction: "Review operator queue before docs refresh.",
            EvidenceLines: ["Queue evidence remains pending reconciliation."],
            UpdatedAtUtc: now.AddMinutes(9));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-continuity-updated-at-skew-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [continuitySignal],
            Consequences: [],
            NextSessionCarryForward: carryForward,
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithCampaignReturnSignalAndUnrelatedCarryForwardTimestampSkew()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        WorkspaceChangePacketProjection campaignReturnSignal = new(
            PacketId: "packet-campaign-return-1",
            Kind: "campaign_return",
            Label: "Campaign return lane update",
            Summary: "Diary and contact return loop remains governed before next session.",
            UpdatedAtUtc: now.AddMinutes(1));
        NextSessionCarryForwardProjection carryForward = new(
            CarryForwardId: "carry-unrelated-campaign-return-1",
            Label: "Operator queue note",
            Summary: "Publication checklist reconciliation is still pending.",
            ReturnSummary: "Workspace governance note remains open.",
            NextSafeAction: "Review operator queue before docs refresh.",
            EvidenceLines: ["Queue evidence remains pending reconciliation."],
            UpdatedAtUtc: now.AddMinutes(9));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-campaign-return-updated-at-skew-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [campaignReturnSignal],
            Consequences: [],
            NextSessionCarryForward: carryForward,
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithOppositionSignalAndUnrelatedCarryForwardTimestampSkew()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        SceneProjection scene = new(
            SceneId: "scene-1",
            RunId: "run-1",
            Title: "Active scene",
            Revision: "r1",
            Status: "active",
            Summary: "Opposition pressure remains active.",
            UpdatedAtUtc: now.AddMinutes(1));
        RunProjection run = new(
            RunId: "run-1",
            CampaignId: "campaign-a",
            Title: "Operation Neon Cradle",
            Status: "active",
            Summary: "Opposition pressure is active on the live run.",
            ActiveSceneId: scene.SceneId,
            Objectives: [],
            Scenes: [scene],
            LatestContinuity: null,
            CreatedAtUtc: now.AddDays(-1),
            UpdatedAtUtc: now.AddMinutes(1));
        NextSessionCarryForwardProjection carryForward = new(
            CarryForwardId: "carry-unrelated-opposition-1",
            Label: "Operator queue note",
            Summary: "Publication checklist reconciliation is still pending.",
            ReturnSummary: "Workspace governance note remains open.",
            NextSafeAction: "Review operator queue before docs refresh.",
            EvidenceLines: ["Queue evidence remains pending reconciliation."],
            UpdatedAtUtc: now.AddMinutes(9));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-opposition-updated-at-skew-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [run],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [],
            Consequences: [],
            NextSessionCarryForward: carryForward,
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithRosterSignalAndUnrelatedCarryForwardTimestampSkew()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        WorkspaceChangePacketProjection rosterSignal = new(
            PacketId: "packet-roster-1",
            Kind: "roster_movement",
            Label: "Roster movement lane update",
            Summary: "Roster transfer window remains governed while receipts hydrate.",
            UpdatedAtUtc: now.AddMinutes(1));
        NextSessionCarryForwardProjection carryForward = new(
            CarryForwardId: "carry-unrelated-roster-1",
            Label: "Operator queue note",
            Summary: "Publication checklist reconciliation is still pending.",
            ReturnSummary: "Workspace governance note remains open.",
            NextSafeAction: "Review operator queue before docs refresh.",
            EvidenceLines: ["Queue evidence remains pending reconciliation."],
            UpdatedAtUtc: now.AddMinutes(9));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-roster-updated-at-skew-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [rosterSignal],
            Consequences: [],
            NextSessionCarryForward: carryForward,
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithPrepLaunchCarryForwardSplitTokensOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        NextSessionCarryForwardProjection carryForward = new(
            CarryForwardId: "carry-1",
            Label: "Prep lane note",
            Summary: "Operator follow-through remains on campaign truth.",
            ReturnSummary: "",
            NextSafeAction: "Launch the queued packet before table return.",
            EvidenceLines: [],
            UpdatedAtUtc: now.AddMinutes(2));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [],
            Consequences: [],
            NextSessionCarryForward: carryForward,
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithPrepLaunchCarryForwardEvidenceSignalsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        NextSessionCarryForwardProjection carryForward = new(
            CarryForwardId: "carry-1",
            Label: "Operator ledger note",
            Summary: "Reconcile queue receipts before publishing.",
            ReturnSummary: "Campaign return handoff remains tracked.",
            NextSafeAction: "Review operator checklist.",
            EvidenceLines: ["Scene prep launch remains queued while launch receipts hydrate."],
            UpdatedAtUtc: now.AddMinutes(2));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [],
            Consequences: [],
            NextSessionCarryForward: carryForward,
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithPrepLaunchSignalAndUnrelatedCarryForwardTimestampSkew()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        WorkspaceChangePacketProjection prepLaunchSignal = new(
            PacketId: "packet-prep-launch-1",
            Kind: "prep_launch",
            Label: "Prep launch lane update",
            Summary: "Prep launch stays governed while launch receipts hydrate.",
            UpdatedAtUtc: now.AddMinutes(1));
        NextSessionCarryForwardProjection carryForward = new(
            CarryForwardId: "carry-unrelated-prep-1",
            Label: "Operator queue note",
            Summary: "Publication checklist reconciliation is still pending.",
            ReturnSummary: "Workspace governance note remains open.",
            NextSafeAction: "Review operator queue before docs refresh.",
            EvidenceLines: ["Queue evidence remains pending reconciliation."],
            UpdatedAtUtc: now.AddMinutes(9));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-prep-launch-updated-at-skew-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [prepLaunchSignal],
            Consequences: [],
            NextSessionCarryForward: carryForward,
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithTravelPrefetchCarryForwardSplitTokensOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        NextSessionCarryForwardProjection carryForward = new(
            CarryForwardId: "carry-1",
            Label: "Travel lane note",
            Summary: "Device handoff stays governed for the same campaign lane.",
            ReturnSummary: "",
            NextSafeAction: "Prefetch sealed offline kit before departure.",
            EvidenceLines: [],
            UpdatedAtUtc: now.AddMinutes(2));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [],
            Consequences: [],
            NextSessionCarryForward: carryForward,
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithTravelPrefetchSignalAndUnrelatedCarryForwardTimestampSkew()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        WorkspaceChangePacketProjection travelPrefetchSignal = new(
            PacketId: "packet-travel-prefetch-1",
            Kind: "travel_prefetch",
            Label: "Travel prefetch lane update",
            Summary: "Travel prefetch stays governed while staging receipts hydrate.",
            UpdatedAtUtc: now.AddMinutes(1));
        NextSessionCarryForwardProjection carryForward = new(
            CarryForwardId: "carry-unrelated-travel-prefetch-1",
            Label: "Operator queue note",
            Summary: "Publication checklist reconciliation is still pending.",
            ReturnSummary: "Workspace governance note remains open.",
            NextSafeAction: "Review operator queue before docs refresh.",
            EvidenceLines: ["Queue evidence remains pending reconciliation."],
            UpdatedAtUtc: now.AddMinutes(9));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-travel-prefetch-updated-at-skew-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [travelPrefetchSignal],
            Consequences: [],
            NextSessionCarryForward: carryForward,
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithEventControlConsequenceKindsSparseOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        CampaignConsequenceProjection heatVariant = new(
            ConsequenceId: "consequence-1",
            Kind: "heat_pressure_lane",
            Label: "",
            State: "elevated",
            Summary: "",
            EvidenceLines: [],
            Receipts: [],
            UpdatedAtUtc: now.AddMinutes(2));
        CampaignConsequenceProjection factionVariant = new(
            ConsequenceId: "consequence-2",
            Kind: "faction_status_window",
            Label: "",
            State: "active",
            Summary: "",
            EvidenceLines: [],
            Receipts: [],
            UpdatedAtUtc: now.AddMinutes(3));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [],
            Consequences: [heatVariant, factionVariant],
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithEventControlKindsAndVerboseCarryForward()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        WorkspaceChangePacketProjection seasonOperation = new(
            PacketId: "packet-1",
            Kind: "season_operation_checkpoint",
            Label: "",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(2));
        CampaignConsequenceProjection heatVariant = new(
            ConsequenceId: "consequence-1",
            Kind: "heat_pressure_lane",
            Label: "",
            State: "elevated",
            Summary: "",
            EvidenceLines: [],
            Receipts: [],
            UpdatedAtUtc: now.AddMinutes(3));
        NextSessionCarryForwardProjection carryForward = new(
            CarryForwardId: "carry-1",
            Label: "Event control lane",
            Summary: "Carry-forward keeps the event board attached to return.",
            ReturnSummary: "Season controls reopen from one governed lane.",
            NextSafeAction: "Reopen event controls before launch.",
            EvidenceLines: [],
            UpdatedAtUtc: now.AddMinutes(4));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [seasonOperation],
            Consequences: [heatVariant],
            NextSessionCarryForward: carryForward,
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithEventControlKindsAndVerboseEventEvidence()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        WorkspaceChangePacketProjection eventSignalA = new(
            PacketId: "event-1",
            Kind: "season_operation_checkpoint",
            Label: "Season board lane A",
            Summary: "Season operation control timeline is saturated with verbose lane details for packet A.",
            UpdatedAtUtc: now.AddMinutes(2));
        WorkspaceChangePacketProjection eventSignalB = new(
            PacketId: "event-2",
            Kind: "event_window_shift",
            Label: "Season board lane B",
            Summary: "Event window control timeline is saturated with verbose lane details for packet B.",
            UpdatedAtUtc: now.AddMinutes(3));
        WorkspaceChangePacketProjection eventSignalC = new(
            PacketId: "event-3",
            Kind: "operation_checkpoint",
            Label: "Season board lane C",
            Summary: "Operation checkpoint control timeline is saturated with verbose lane details for packet C.",
            UpdatedAtUtc: now.AddMinutes(4));
        CampaignConsequenceProjection heatVariant = new(
            ConsequenceId: "consequence-1",
            Kind: "heat_pressure_lane",
            Label: "",
            State: "active",
            Summary: "",
            EvidenceLines: [],
            Receipts: [],
            UpdatedAtUtc: now.AddMinutes(5));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [eventSignalA, eventSignalB, eventSignalC],
            Consequences: [heatVariant],
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithEventControlExplicitEventSignalsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        WorkspaceChangePacketProjection eventWindowShift = new(
            PacketId: "packet-1",
            Kind: "event_window_shift",
            Label: "Event window shift",
            Summary: "Event window shift keeps timeline governance visible while derivative receipt families catch up.",
            UpdatedAtUtc: now.AddMinutes(1));
        WorkspaceChangePacketProjection seasonOpsCheckpoint = new(
            PacketId: "packet-2",
            Kind: "season_operation_checkpoint",
            Label: "Season operation checkpoint",
            Summary: "Season operation checkpoint preserves operator timeline control on the same governed lane.",
            UpdatedAtUtc: now.AddMinutes(2));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [eventWindowShift, seasonOpsCheckpoint],
            Consequences: [],
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithCompactEventControlSignalsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        WorkspaceChangePacketProjection eventControlCompact = new(
            PacketId: "packet-compact-eventcontrol",
            Kind: "eventcontrol_shift",
            Label: "Eventcontrol window shift",
            Summary: "Eventcontrol board remains active while canonical event receipts hydrate.",
            UpdatedAtUtc: now.AddMinutes(1));
        WorkspaceChangePacketProjection seasonOpsCompact = new(
            PacketId: "packet-compact-seasonops",
            Kind: "seasonops_checkpoint",
            Label: "Seasonops checkpoint",
            Summary: "Seasonops timeline remains governed for the next launch gate.",
            UpdatedAtUtc: now.AddMinutes(2));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-compact-eventcontrol-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [eventControlCompact, seasonOpsCompact],
            Consequences: [],
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithCompactSeasonOpSignalOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        WorkspaceChangePacketProjection seasonOpCompact = new(
            PacketId: "packet-compact-seasonop",
            Kind: "seasonop_checkpoint",
            Label: "Seasonop checkpoint",
            Summary: "Seasonop timeline remains governed for the next launch gate.",
            UpdatedAtUtc: now.AddMinutes(2));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-compact-seasonop-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [seasonOpCompact],
            Consequences: [],
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithCompactEventCtrlSignalOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        WorkspaceChangePacketProjection eventCtrlCompact = new(
            PacketId: "packet-compact-eventctrl",
            Kind: "eventctrl_checkpoint",
            Label: "Eventctrl checkpoint",
            Summary: "Eventctrl board remains governed for the next launch gate.",
            UpdatedAtUtc: now.AddMinutes(2));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-compact-eventctrl-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [eventCtrlCompact],
            Consequences: [],
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithCompactPrepLaunchAndTravelPrefetchSignalsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        WorkspaceChangePacketProjection compactPrepLaunch = new(
            PacketId: "packet-compact-preplaunch",
            Kind: "preplaunch_window",
            Label: "Preplaunch window",
            Summary: "Preplaunch queue remains governed while canonical launch receipts hydrate.",
            UpdatedAtUtc: now.AddMinutes(1));
        WorkspaceChangePacketProjection compactTravelPrefetch = new(
            PacketId: "packet-compact-travelprefetch",
            Kind: "travelprefetch_window",
            Label: "Travelprefetch window",
            Summary: "Travelprefetch queue remains governed for return-device staging.",
            UpdatedAtUtc: now.AddMinutes(2));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-compact-preplaunch-travelprefetch-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [compactPrepLaunch, compactTravelPrefetch],
            Consequences: [],
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithRosterSignalsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        ObjectiveProjection objective = new(
            ObjectiveId: "objective-1",
            Title: "Roster handoff review",
            Status: "open",
            Pressure: "medium",
            Summary: "Crew assignment handoff still needs organizer approval before session launch.",
            UpdatedAtUtc: now.AddMinutes(2));

        RunProjection run = new(
            RunId: "run-1",
            CampaignId: "campaign-a",
            Title: "Dockyard pressure test",
            Status: "active",
            Summary: "Current run remains active.",
            ActiveSceneId: null,
            Objectives: [objective],
            Scenes: [],
            LatestContinuity: null,
            CreatedAtUtc: now.AddDays(-1),
            UpdatedAtUtc: now.AddMinutes(3));

        WorkspaceChangePacketProjection rosterChange = new(
            PacketId: "packet-1",
            Kind: "roster_assignment",
            Label: "Crew assignment update",
            Summary: "Roster assignment moved a runner into season operations coverage.",
            UpdatedAtUtc: now.AddMinutes(4));

        NextSessionCarryForwardProjection carryForward = new(
            CarryForwardId: "carry-1",
            Label: "Roster return carry-forward",
            Summary: "Roster handoff decisions stay governed before the next session opens.",
            ReturnSummary: "Crew assignment posture remains attached to the return lane.",
            NextSafeAction: "Resolve roster assignment before launching event prep.",
            EvidenceLines: ["Carry-forward receipt captured for roster return."],
            UpdatedAtUtc: now.AddMinutes(5));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [run],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [rosterChange],
            Consequences: [],
            NextSessionCarryForward: carryForward);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithRosterSignalLabelsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        ObjectiveProjection objective = new(
            ObjectiveId: "objective-1",
            Title: "Roster handoff label",
            Status: "open",
            Pressure: "medium",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(2));

        RunProjection run = new(
            RunId: "run-1",
            CampaignId: "campaign-a",
            Title: "Dockyard pressure test",
            Status: "active",
            Summary: "Current run remains active.",
            ActiveSceneId: null,
            Objectives: [objective],
            Scenes: [],
            LatestContinuity: null,
            CreatedAtUtc: now.AddDays(-1),
            UpdatedAtUtc: now.AddMinutes(3));

        WorkspaceChangePacketProjection rosterChange = new(
            PacketId: "packet-1",
            Kind: "roster_assignment",
            Label: "Crew assignment label",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(4));

        NextSessionCarryForwardProjection carryForward = new(
            CarryForwardId: "carry-1",
            Label: "Roster return label",
            Summary: "",
            ReturnSummary: "",
            NextSafeAction: "",
            EvidenceLines: [],
            UpdatedAtUtc: now.AddMinutes(5));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [run],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [rosterChange],
            Consequences: [],
            NextSessionCarryForward: carryForward);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithRosterSignalKindsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        ObjectiveProjection objective = new(
            ObjectiveId: "objective-1",
            Title: "Roster handoff label",
            Status: "open",
            Pressure: "medium",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(2));

        RunProjection run = new(
            RunId: "run-1",
            CampaignId: "campaign-a",
            Title: "Dockyard pressure test",
            Status: "active",
            Summary: "Current run remains active.",
            ActiveSceneId: null,
            Objectives: [objective],
            Scenes: [],
            LatestContinuity: null,
            CreatedAtUtc: now.AddDays(-1),
            UpdatedAtUtc: now.AddMinutes(3));

        WorkspaceChangePacketProjection rosterChange = new(
            PacketId: "packet-1",
            Kind: "roster_assignment",
            Label: "",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(4));

        NextSessionCarryForwardProjection carryForward = new(
            CarryForwardId: "carry-1",
            Label: "",
            Summary: "",
            ReturnSummary: "",
            NextSafeAction: "",
            EvidenceLines: [],
            UpdatedAtUtc: now.AddMinutes(5));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [run],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [rosterChange],
            Consequences: [],
            NextSessionCarryForward: carryForward);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithRosterSparseSignalKindsAndLabelsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        ObjectiveProjection objective = new(
            ObjectiveId: "objective-1",
            Title: "Roster handoff label",
            Status: "open",
            Pressure: "medium",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(2));

        RunProjection run = new(
            RunId: "run-1",
            CampaignId: "campaign-a",
            Title: "Dockyard pressure test",
            Status: "active",
            Summary: "Current run remains active.",
            ActiveSceneId: null,
            Objectives: [objective],
            Scenes: [],
            LatestContinuity: null,
            CreatedAtUtc: now.AddDays(-1),
            UpdatedAtUtc: now.AddMinutes(3));

        WorkspaceChangePacketProjection rosterChange = new(
            PacketId: "packet-1",
            Kind: "",
            Label: "Crew assignment label",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(4));

        NextSessionCarryForwardProjection carryForward = new(
            CarryForwardId: "carry-1",
            Label: "Roster return label",
            Summary: "",
            ReturnSummary: "",
            NextSafeAction: "",
            EvidenceLines: [],
            UpdatedAtUtc: now.AddMinutes(5));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [run],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [rosterChange],
            Consequences: [],
            NextSessionCarryForward: carryForward);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithRosterSplitMovementSignalTokens()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        ObjectiveProjection objective = new(
            ObjectiveId: "objective-1",
            Title: "Roster handoff board",
            Status: "open",
            Pressure: "medium",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(2));

        RunProjection run = new(
            RunId: "run-1",
            CampaignId: "campaign-a",
            Title: "Dockyard pressure test",
            Status: "active",
            Summary: "Current run remains active.",
            ActiveSceneId: null,
            Objectives: [objective],
            Scenes: [],
            LatestContinuity: null,
            CreatedAtUtc: now.AddDays(-1),
            UpdatedAtUtc: now.AddMinutes(3));

        WorkspaceChangePacketProjection rosterChange = new(
            PacketId: "packet-1",
            Kind: "roster",
            Label: "Movement board label",
            Summary: "Continuity board wording only.",
            UpdatedAtUtc: now.AddMinutes(4));

        NextSessionCarryForwardProjection carryForward = new(
            CarryForwardId: "carry-1",
            Label: "Carry-forward label",
            Summary: "",
            ReturnSummary: "",
            NextSafeAction: "",
            EvidenceLines: [],
            UpdatedAtUtc: now.AddMinutes(5));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [run],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [rosterChange],
            Consequences: [],
            NextSessionCarryForward: carryForward);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithCompactRosterMovementSignalsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        ObjectiveProjection objective = new(
            ObjectiveId: "objective-compact-roster-1",
            Title: "Rostermove handoff review",
            Status: "open",
            Pressure: "medium",
            Summary: "Rostermove queue remains pending until crewhandoff approval lands.",
            UpdatedAtUtc: now.AddMinutes(2));

        RunProjection run = new(
            RunId: "run-compact-roster-1",
            CampaignId: "campaign-a",
            Title: "Dockyard roster pressure test",
            Status: "active",
            Summary: "Current run remains active under compact roster transfer pressure.",
            ActiveSceneId: null,
            Objectives: [objective],
            Scenes: [],
            LatestContinuity: null,
            CreatedAtUtc: now.AddDays(-1),
            UpdatedAtUtc: now.AddMinutes(3));

        WorkspaceChangePacketProjection compactRosterSignal = new(
            PacketId: "packet-compact-roster-1",
            Kind: "rostermove_signal",
            Label: "Rostermove checkpoint",
            Summary: "Rostermove queue keeps runner assignment governed without local shadow notes.",
            UpdatedAtUtc: now.AddMinutes(4));

        NextSessionCarryForwardProjection carryForward = new(
            CarryForwardId: "carry-compact-roster-1",
            Label: "Crewhandoff carry-forward",
            Summary: "Crewhandoff remains pending for the next session return loop.",
            ReturnSummary: "Compact roster movement posture remains attached to campaign return.",
            NextSafeAction: "Close crewhandoff approvals before launch.",
            EvidenceLines: ["Rostermove receipt line remains open for this return."],
            UpdatedAtUtc: now.AddMinutes(5));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-compact-roster-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [run],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [compactRosterSignal],
            Consequences: [],
            NextSessionCarryForward: carryForward);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithRosterConsequenceKindsSparseOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        CampaignConsequenceProjection rosterConsequence = new(
            ConsequenceId: "consequence-1",
            Kind: "roster_assignment",
            Label: "",
            State: "active",
            Summary: "",
            EvidenceLines: [],
            Receipts: [],
            UpdatedAtUtc: now.AddMinutes(4));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [],
            Consequences: [rosterConsequence],
            RosterTransfers: [],
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithRosterConsequenceLabelOnlyAndSparseKind()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        CampaignConsequenceProjection rosterConsequence = new(
            ConsequenceId: "consequence-1",
            Kind: "",
            Label: "Roster movement consequence label",
            State: "active",
            Summary: "",
            EvidenceLines: [],
            Receipts: [],
            UpdatedAtUtc: now.AddMinutes(4));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [],
            Consequences: [rosterConsequence],
            RosterTransfers: [],
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithRosterTransfersSparseOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        RosterTransferProjection transfer = new(
            TransferId: "transfer-1",
            DossierId: "dossier-1",
            RunnerHandle: "Ghostline",
            PreviousOwnerUserId: "user-a",
            CurrentOwnerUserId: "user-b",
            SourceGroupId: "group-a",
            SourceGroupName: "Night Shift",
            SourceCampaignId: "campaign-a",
            SourceCampaignName: "Neon Cradle",
            SourceCrewId: "crew-a",
            SourceCrewName: "Wardens",
            TargetGroupId: "group-b",
            TargetGroupName: "Aftermath Desk",
            TargetCampaignId: "campaign-b",
            TargetCampaignName: "Season Ops",
            TargetCrewId: "crew-b",
            TargetCrewName: "Season Operations Roster",
            InitiatedByUserId: "gm-1",
            Summary: "",
            AuditLines: [],
            Receipts: [],
            TransferredAtUtc: now.AddMinutes(3));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [],
            Consequences: [],
            RosterTransfers: [transfer],
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithRosterTransfersSparseAndVerboseOpsEvidence()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        RosterTransferProjection transfer = new(
            TransferId: "transfer-1",
            DossierId: "dossier-1",
            RunnerHandle: "Ghostline",
            PreviousOwnerUserId: "user-a",
            CurrentOwnerUserId: "user-b",
            SourceGroupId: "group-a",
            SourceGroupName: "Night Shift",
            SourceCampaignId: "campaign-a",
            SourceCampaignName: "Neon Cradle",
            SourceCrewId: "crew-a",
            SourceCrewName: "Wardens",
            TargetGroupId: "group-b",
            TargetGroupName: "Aftermath Desk",
            TargetCampaignId: "campaign-b",
            TargetCampaignName: "Season Ops",
            TargetCrewId: "crew-b",
            TargetCrewName: "Season Operations Roster",
            InitiatedByUserId: "gm-1",
            Summary: "",
            AuditLines:
            [
                "Transfer receipt line A includes verbose season-operation context for launch prep and roster pressure.",
                "Transfer receipt line B includes verbose staffing context for event windows and checkpoint planning.",
                "Transfer receipt line C includes verbose accountability context for operator lane governance."
            ],
            Receipts: [],
            TransferredAtUtc: now.AddMinutes(3));

        WorkspaceChangePacketProjection rosterSignal = new(
            PacketId: "packet-roster",
            Kind: "roster_assignment",
            Label: "",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(4));
        WorkspaceChangePacketProjection eventSignalA = new(
            PacketId: "packet-event-a",
            Kind: "season_operation_checkpoint",
            Label: "Season board lane A",
            Summary: "Season operation control timeline is saturated with verbose lane details for packet A.",
            UpdatedAtUtc: now.AddMinutes(5));
        WorkspaceChangePacketProjection eventSignalB = new(
            PacketId: "packet-event-b",
            Kind: "event_window_shift",
            Label: "Season board lane B",
            Summary: "Event window control timeline is saturated with verbose lane details for packet B.",
            UpdatedAtUtc: now.AddMinutes(6));
        WorkspaceChangePacketProjection eventSignalC = new(
            PacketId: "packet-event-c",
            Kind: "operation_checkpoint",
            Label: "Season board lane C",
            Summary: "Operation checkpoint control timeline is saturated with verbose lane details for packet C.",
            UpdatedAtUtc: now.AddMinutes(7));

        CampaignConsequenceProjection consequence = new(
            ConsequenceId: "consequence-1",
            Kind: "heat_pressure_lane",
            Label: "Heat pressure lane",
            State: "active",
            Summary: "Heat pressure remains attached to event-control governance.",
            EvidenceLines: [],
            Receipts: [],
            UpdatedAtUtc: now.AddMinutes(8));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [rosterSignal, eventSignalA, eventSignalB, eventSignalC],
            Consequences: [consequence],
            RosterTransfers: [transfer],
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithEventControlRunPressureSignalsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        ObjectiveProjection objective = new(
            ObjectiveId: "objective-1",
            Title: "Season event window lock",
            Status: "open",
            Pressure: "high",
            Summary: "Event window remains open until organizer controls are reconciled.",
            UpdatedAtUtc: now.AddMinutes(2));

        SceneProjection scene = new(
            SceneId: "scene-1",
            RunId: "run-1",
            Title: "Season-control checkpoint",
            Revision: "r4",
            Status: "active",
            Summary: "Event control board stays active while the return lane is validated.",
            UpdatedAtUtc: now.AddMinutes(3));

        RunProjection run = new(
            RunId: "run-1",
            CampaignId: "campaign-a",
            Title: "Dockyard pressure test",
            Status: "active",
            Summary: "Current run remains active under season-control pressure.",
            ActiveSceneId: "scene-1",
            Objectives: [objective],
            Scenes: [scene],
            LatestContinuity: null,
            CreatedAtUtc: now.AddDays(-1),
            UpdatedAtUtc: now.AddMinutes(4));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [run],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [],
            Consequences: [],
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithEventControlRosterTransfersOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        RosterTransferProjection transfer = new(
            TransferId: "transfer-1",
            DossierId: "dossier-1",
            RunnerHandle: "Ghostline",
            PreviousOwnerUserId: "user-a",
            CurrentOwnerUserId: "user-b",
            SourceGroupId: "group-a",
            SourceGroupName: "Night Shift",
            SourceCampaignId: "campaign-a",
            SourceCampaignName: "Neon Cradle",
            SourceCrewId: "crew-a",
            SourceCrewName: "Wardens",
            TargetGroupId: "group-b",
            TargetGroupName: "Aftermath Desk",
            TargetCampaignId: "campaign-b",
            TargetCampaignName: "Season Ops",
            TargetCrewId: "crew-b",
            TargetCrewName: "Season Operations Roster",
            InitiatedByUserId: "gm-1",
            Summary: "Moved Ghostline into season operations roster lane.",
            AuditLines: ["Roster movement receipt captured for season operations."],
            Receipts: [],
            TransferredAtUtc: now.AddMinutes(3));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [],
            Consequences: [],
            RosterTransfers: [transfer],
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithEventControlOppositionSignalsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        WorkspaceChangePacketProjection oppositionVariant = new(
            PacketId: "packet-1",
            Kind: "opposition_window_shift",
            Label: "Opposition window shift",
            Summary: "Opposition command board remains active while event-control receipts catch up.",
            UpdatedAtUtc: now.AddMinutes(2));

        ObjectiveProjection objective = new(
            ObjectiveId: "objective-1",
            Title: "Hostile response window",
            Status: "open",
            Pressure: "high",
            Summary: "Hostile pressure remains active until the organizer event board is reopened.",
            UpdatedAtUtc: now.AddMinutes(3));

        SceneProjection scene = new(
            SceneId: "scene-1",
            RunId: "run-1",
            Title: "Dockyard opposition board",
            Revision: "r6",
            Status: "active",
            Summary: "Opposition command board remains active for the next season-control checkpoint.",
            UpdatedAtUtc: now.AddMinutes(4));

        RunProjection run = new(
            RunId: "run-1",
            CampaignId: "campaign-a",
            Title: "Dockyard pressure test",
            Status: "active",
            Summary: "Current run remains active under hostile pressure.",
            ActiveSceneId: "scene-1",
            Objectives: [objective],
            Scenes: [scene],
            LatestContinuity: null,
            CreatedAtUtc: now.AddDays(-1),
            UpdatedAtUtc: now.AddMinutes(5));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [run],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [oppositionVariant],
            Consequences: [],
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithOppositionCarryForwardSignalsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        NextSessionCarryForwardProjection carryForward = new(
            CarryForwardId: "carry-1",
            Label: "Opposition lane carry-forward",
            Summary: "Opposition pressure remains active while receipts hydrate.",
            ReturnSummary: "Threat response window stays governed for next reopen.",
            NextSafeAction: "Review opposition board before launch.",
            EvidenceLines: [],
            UpdatedAtUtc: now.AddMinutes(2));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [],
            Consequences: [],
            NextSessionCarryForward: carryForward,
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithOppositionCarryForwardEvidenceSignalsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        NextSessionCarryForwardProjection carryForward = new(
            CarryForwardId: "carry-1",
            Label: "Operator lane note",
            Summary: "Queue reconciliation remains pending.",
            ReturnSummary: "Carry-forward handoff remains tracked.",
            NextSafeAction: "Review operator checklist.",
            EvidenceLines: ["Threat window remains active while the opposition board is reopened."],
            UpdatedAtUtc: now.AddMinutes(2));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [],
            Consequences: [],
            NextSessionCarryForward: carryForward,
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithThreatModelCarryForwardOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        NextSessionCarryForwardProjection carryForward = new(
            CarryForwardId: "carry-threat-model-1",
            Label: "Threat model carry-forward",
            Summary: "Threat model backlog remains queued for architecture review.",
            ReturnSummary: "Capture threat model updates in the governance log.",
            NextSafeAction: "Review threat model checklist before publishing docs.",
            EvidenceLines: ["Threat model worksheet remains open for documentation signoff."],
            UpdatedAtUtc: now.AddMinutes(2));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-threat-model-carry-forward-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [],
            Consequences: [],
            NextSessionCarryForward: carryForward,
            PrepLaunches: [],
            TravelPrefetches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithOppositionChangeSignalsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        WorkspaceChangePacketProjection oppositionWindow = new(
            PacketId: "packet-1",
            Kind: "opposition_window_shift",
            Label: "Opposition window shift",
            Summary: "Opposition window shift keeps threat posture visible before consequence or run-pressure summaries arrive.",
            UpdatedAtUtc: now.AddMinutes(1));
        WorkspaceChangePacketProjection threatLane = new(
            PacketId: "packet-2",
            Kind: "threat_control_delta",
            Label: "Threat control delta",
            Summary: "Threat control delta remains attached to the governed opposition lane.",
            UpdatedAtUtc: now.AddMinutes(2));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [oppositionWindow, threatLane],
            Consequences: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithEncounterEnemyAndOpforSignalsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        WorkspaceChangePacketProjection encounterWindow = new(
            PacketId: "packet-encounter",
            Kind: "encounter_window_shift",
            Label: "Encounter window shift",
            Summary: "Encounter command board stays active while receipts hydrate.",
            UpdatedAtUtc: now.AddMinutes(1));
        WorkspaceChangePacketProjection opforWindow = new(
            PacketId: "packet-opfor",
            Kind: "opfor_window_shift",
            Label: "Opfor lane shift",
            Summary: "Opfor enemy window remains active for the next control reopen.",
            UpdatedAtUtc: now.AddMinutes(2));

        ObjectiveProjection objective = new(
            ObjectiveId: "objective-enemy-1",
            Title: "Enemy response window",
            Status: "open",
            Pressure: "high",
            Summary: "Enemy pressure remains active until the board reopens.",
            UpdatedAtUtc: now.AddMinutes(3));

        RunProjection run = new(
            RunId: "run-encounter-opfor-1",
            CampaignId: "campaign-a",
            Title: "Dockyard encounter pressure",
            Status: "active",
            Summary: "Current run remains active under encounter and opfor pressure.",
            ActiveSceneId: null,
            Objectives: [objective],
            Scenes: [],
            LatestContinuity: null,
            CreatedAtUtc: now.AddDays(-1),
            UpdatedAtUtc: now.AddMinutes(4));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-encounter-opfor-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [run],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [encounterWindow, opforWindow],
            Consequences: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithOpForAndOpforceSignalsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        WorkspaceChangePacketProjection opForWindow = new(
            PacketId: "packet-op-for",
            Kind: "op_for_window_shift",
            Label: "Op_for lane shift",
            Summary: "Op_for enemy window remains active for the next control reopen.",
            UpdatedAtUtc: now.AddMinutes(1));
        WorkspaceChangePacketProjection opforceWindow = new(
            PacketId: "packet-opforce",
            Kind: "opforce_window_shift",
            Label: "Opforce lane shift",
            Summary: "Opforce response board remains active while canonical receipts hydrate.",
            UpdatedAtUtc: now.AddMinutes(2));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-op-for-opforce-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [opForWindow, opforceWindow],
            Consequences: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithOppositionSignalLabelsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        WorkspaceChangePacketProjection oppositionWindow = new(
            PacketId: "packet-1",
            Kind: "opposition_window_shift",
            Label: "Opposition window label",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(1));
        WorkspaceChangePacketProjection threatLane = new(
            PacketId: "packet-2",
            Kind: "threat_control_delta",
            Label: "Threat lane label",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(2));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [oppositionWindow, threatLane],
            Consequences: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithOppositionKindsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        WorkspaceChangePacketProjection oppositionWindow = new(
            PacketId: "packet-1",
            Kind: "opposition_window",
            Label: "",
            Summary: "Opposition window remains active.",
            UpdatedAtUtc: now.AddMinutes(1));
        WorkspaceChangePacketProjection threatWindow = new(
            PacketId: "packet-2",
            Kind: "threat_window",
            Label: "",
            Summary: "Threat window remains active.",
            UpdatedAtUtc: now.AddMinutes(2));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [oppositionWindow, threatWindow],
            Consequences: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithOppositionSparseSignalKindsAndLabelsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        WorkspaceChangePacketProjection oppositionWindow = new(
            PacketId: "packet-1",
            Kind: "",
            Label: "Opposition window label",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(1));
        WorkspaceChangePacketProjection threatLane = new(
            PacketId: "packet-2",
            Kind: "",
            Label: "Threat lane label",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(2));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [oppositionWindow, threatLane],
            Consequences: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithOppositionConsequenceKindsSparseOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        CampaignConsequenceProjection oppositionWindow = new(
            ConsequenceId: "consequence-1",
            Kind: "opposition_window",
            Label: "",
            State: "active",
            Summary: "",
            EvidenceLines: [],
            Receipts: [],
            UpdatedAtUtc: now.AddMinutes(1));
        CampaignConsequenceProjection threatWindow = new(
            ConsequenceId: "consequence-2",
            Kind: "threat_window",
            Label: "",
            State: "active",
            Summary: "",
            EvidenceLines: [],
            Receipts: [],
            UpdatedAtUtc: now.AddMinutes(2));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [],
            Consequences: [oppositionWindow, threatWindow]);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithOppositionConsequenceKindsSparseAndVerboseSignals()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        WorkspaceChangePacketProjection oppositionWindowSignal = new(
            PacketId: "packet-1",
            Kind: "opposition_window_shift",
            Label: "Opposition window label",
            Summary: "Opposition window summary line remains verbose in evidence.",
            UpdatedAtUtc: now.AddMinutes(3));
        WorkspaceChangePacketProjection threatWindowSignal = new(
            PacketId: "packet-2",
            Kind: "threat_window_shift",
            Label: "Threat window label",
            Summary: "Threat window summary line remains verbose in evidence.",
            UpdatedAtUtc: now.AddMinutes(4));

        CampaignConsequenceProjection sparseConsequence = new(
            ConsequenceId: "consequence-1",
            Kind: "threat_window",
            Label: "",
            State: "active",
            Summary: "",
            EvidenceLines: [],
            Receipts: [],
            UpdatedAtUtc: now.AddMinutes(2));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [oppositionWindowSignal, threatWindowSignal],
            Consequences: [sparseConsequence]);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithMixedOppositionAndRelationshipConsequences()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        CampaignConsequenceProjection opposition = new(
            ConsequenceId: "consequence-1",
            Kind: "threat_window",
            Label: "",
            State: "active",
            Summary: "",
            EvidenceLines: [],
            Receipts: [],
            UpdatedAtUtc: now.AddMinutes(2));
        CampaignConsequenceProjection relationship = new(
            ConsequenceId: "consequence-2",
            Kind: "heat_pressure_lane",
            Label: "Heat pressure lane",
            State: "active",
            Summary: "Heat pressure remains attached to event-control governance.",
            EvidenceLines: ["Heat pressure receipt line"],
            Receipts: [],
            UpdatedAtUtc: now.AddMinutes(3));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [],
            Consequences: [opposition, relationship]);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithOppositionConsequenceLabelOnlyAndSparseKind()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        CampaignConsequenceProjection sparseConsequence = new(
            ConsequenceId: "consequence-1",
            Kind: "",
            Label: "Opposition window label",
            State: "active",
            Summary: "",
            EvidenceLines: [],
            Receipts: [],
            UpdatedAtUtc: now.AddMinutes(2));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [],
            Consequences: [sparseConsequence]);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithPrepLaunchChangeSignalsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        ObjectiveProjection objective = new(
            ObjectiveId: "objective-1",
            Title: "Prep launch validation",
            Status: "open",
            Pressure: "medium",
            Summary: "Prep launch evidence is pending final receipt ingestion.",
            UpdatedAtUtc: now.AddMinutes(2));

        RunProjection run = new(
            RunId: "run-1",
            CampaignId: "campaign-a",
            Title: "Dockyard pressure test",
            Status: "active",
            Summary: "Current run remains active.",
            ActiveSceneId: null,
            Objectives: [objective],
            Scenes: [],
            LatestContinuity: null,
            CreatedAtUtc: now.AddDays(-1),
            UpdatedAtUtc: now.AddMinutes(3));

        WorkspaceChangePacketProjection prepLaunchChange = new(
            PacketId: "packet-1",
            Kind: "prep_launch",
            Label: "Scene prep launch",
            Summary: "Prep launch packet was staged on the governed campaign lane.",
            UpdatedAtUtc: now.AddMinutes(4));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [run],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [prepLaunchChange],
            Consequences: [],
            PrepLaunches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithPrepLaunchSignalLabelsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        ObjectiveProjection objective = new(
            ObjectiveId: "objective-1",
            Title: "Prep launch validation",
            Status: "open",
            Pressure: "medium",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(2));

        RunProjection run = new(
            RunId: "run-1",
            CampaignId: "campaign-a",
            Title: "Dockyard pressure test",
            Status: "active",
            Summary: "Current run remains active.",
            ActiveSceneId: null,
            Objectives: [objective],
            Scenes: [],
            LatestContinuity: null,
            CreatedAtUtc: now.AddDays(-1),
            UpdatedAtUtc: now.AddMinutes(3));

        WorkspaceChangePacketProjection prepLaunchChange = new(
            PacketId: "packet-1",
            Kind: "prep_launch",
            Label: "Scene prep label",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(4));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [run],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [prepLaunchChange],
            Consequences: [],
            PrepLaunches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithPrepLaunchKindsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        ObjectiveProjection objective = new(
            ObjectiveId: "objective-1",
            Title: "Prep launch validation",
            Status: "open",
            Pressure: "medium",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(2));

        RunProjection run = new(
            RunId: "run-1",
            CampaignId: "campaign-a",
            Title: "Dockyard pressure test",
            Status: "active",
            Summary: "Current run remains active.",
            ActiveSceneId: null,
            Objectives: [objective],
            Scenes: [],
            LatestContinuity: null,
            CreatedAtUtc: now.AddDays(-1),
            UpdatedAtUtc: now.AddMinutes(3));

        WorkspaceChangePacketProjection prepLaunchChange = new(
            PacketId: "packet-1",
            Kind: "prep_launch",
            Label: "",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(4));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [run],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [prepLaunchChange],
            Consequences: [],
            PrepLaunches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithPrepLaunchSparseSignalKindsAndLabelsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        ObjectiveProjection objective = new(
            ObjectiveId: "objective-1",
            Title: "Prep launch validation",
            Status: "open",
            Pressure: "medium",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(2));

        RunProjection run = new(
            RunId: "run-1",
            CampaignId: "campaign-a",
            Title: "Dockyard pressure test",
            Status: "active",
            Summary: "Current run remains active.",
            ActiveSceneId: null,
            Objectives: [objective],
            Scenes: [],
            LatestContinuity: null,
            CreatedAtUtc: now.AddDays(-1),
            UpdatedAtUtc: now.AddMinutes(3));

        WorkspaceChangePacketProjection prepLaunchChange = new(
            PacketId: "packet-1",
            Kind: "",
            Label: "Scene prep launch label",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(4));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [run],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [prepLaunchChange],
            Consequences: [],
            PrepLaunches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithPrepLaunchSparseSignalKindsAndSplitTokens()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        ObjectiveProjection objective = new(
            ObjectiveId: "objective-1",
            Title: "Prep launch validation",
            Status: "open",
            Pressure: "medium",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(2));

        RunProjection run = new(
            RunId: "run-1",
            CampaignId: "campaign-a",
            Title: "Dockyard pressure test",
            Status: "active",
            Summary: "Current run remains active.",
            ActiveSceneId: null,
            Objectives: [objective],
            Scenes: [],
            LatestContinuity: null,
            CreatedAtUtc: now.AddDays(-1),
            UpdatedAtUtc: now.AddMinutes(3));

        WorkspaceChangePacketProjection prepLaunchChange = new(
            PacketId: "packet-1",
            Kind: "",
            Label: "Scene prep label",
            Summary: "Launch window pending final check.",
            UpdatedAtUtc: now.AddMinutes(4));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [run],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [prepLaunchChange],
            Consequences: [],
            PrepLaunches: []);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithPrepLaunchKindsAndVerboseLaunchEvidence()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        ObjectiveProjection objective = new(
            ObjectiveId: "objective-1",
            Title: "Prep launch validation",
            Status: "open",
            Pressure: "medium",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(2));

        RunProjection run = new(
            RunId: "run-1",
            CampaignId: "campaign-a",
            Title: "Dockyard pressure test",
            Status: "active",
            Summary: "Current run remains active.",
            ActiveSceneId: null,
            Objectives: [objective],
            Scenes: [],
            LatestContinuity: null,
            CreatedAtUtc: now.AddDays(-1),
            UpdatedAtUtc: now.AddMinutes(3));

        WorkspaceChangePacketProjection prepLaunchChange = new(
            PacketId: "packet-1",
            Kind: "prep_launch",
            Label: "",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(4));

        GovernedPrepLaunchProjection launchA = new(
            LaunchId: "launch-1",
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            PacketId: "scene:workspace-1",
            PacketKind: "scene_packet",
            PacketTitle: "Season prep lane A",
            TargetRunId: "run-1",
            TargetRunTitle: "Dockyard pressure test",
            TargetSceneId: "scene-a",
            TargetSceneTitle: "Pier ingress",
            InitiatedByUserId: "gm-1",
            Summary: "Season prep lane A remains richly documented for launch audit detail.",
            AuditLines: ["Launch lane A audit details are fully populated."],
            LaunchedAtUtc: now.AddMinutes(8));
        GovernedPrepLaunchProjection launchB = new(
            LaunchId: "launch-2",
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            PacketId: "scene:workspace-2",
            PacketKind: "scene_packet",
            PacketTitle: "Season prep lane B",
            TargetRunId: "run-1",
            TargetRunTitle: "Dockyard pressure test",
            TargetSceneId: "scene-b",
            TargetSceneTitle: "Signal tunnel",
            InitiatedByUserId: "gm-1",
            Summary: "Season prep lane B remains richly documented for launch audit detail.",
            AuditLines: ["Launch lane B audit details are fully populated."],
            LaunchedAtUtc: now.AddMinutes(7));
        GovernedPrepLaunchProjection launchC = new(
            LaunchId: "launch-3",
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            PacketId: "scene:workspace-3",
            PacketKind: "scene_packet",
            PacketTitle: "Season prep lane C",
            TargetRunId: "run-1",
            TargetRunTitle: "Dockyard pressure test",
            TargetSceneId: "scene-c",
            TargetSceneTitle: "Grid relay",
            InitiatedByUserId: "gm-1",
            Summary: "Season prep lane C remains richly documented for launch audit detail.",
            AuditLines: ["Launch lane C audit details are fully populated."],
            LaunchedAtUtc: now.AddMinutes(6));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [run],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [prepLaunchChange],
            Consequences: [],
            PrepLaunches: [launchA, launchB, launchC]);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithContinuitySignalsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        WorkspaceChangePacketProjection continuityChange = new(
            PacketId: "packet-1",
            Kind: "next_session_carry_forward",
            Label: "Continuity carry-forward packet",
            Summary: "Continuity carry-forward remains governed on the shared campaign lane.",
            UpdatedAtUtc: now.AddMinutes(3));

        NextSessionCarryForwardProjection carryForward = new(
            CarryForwardId: "carry-1",
            Label: "Continuity return lane",
            Summary: "Carry-forward continuity signal remains active for the next session.",
            ReturnSummary: "Return lane continuity is ready for shared reopen.",
            NextSafeAction: "Review carry-forward continuity before starting play.",
            EvidenceLines: ["Carry-forward continuity receipt captured."],
            UpdatedAtUtc: now.AddMinutes(4));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [continuityChange],
            Consequences: [],
            NextSessionCarryForward: carryForward);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithUnrelatedContinuityCarryForwardNotesOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        NextSessionCarryForwardProjection carryForward = new(
            CarryForwardId: "carry-unrelated-continuity-1",
            Label: "Planning board note",
            Summary: "Program backlog tracking remains under review in this operator-only note.",
            ReturnSummary: "Queue status remains unchanged while approval review is pending.",
            NextSafeAction: "Schedule governance review after staffing sync.",
            EvidenceLines: ["No campaign continuity payload has been attached to this planning note."],
            UpdatedAtUtc: now.AddMinutes(4));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-unrelated-continuity-carry-forward-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [],
            Consequences: [],
            NextSessionCarryForward: carryForward);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithContinuityCarryForwardEvidenceSignalsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        NextSessionCarryForwardProjection carryForward = new(
            CarryForwardId: "carry-continuity-evidence-1",
            Label: "",
            Summary: "",
            ReturnSummary: "",
            NextSafeAction: "",
            EvidenceLines:
            [
                "Campaign continuity lane remains open for next-session return.",
                "Carry forward continuity handoff is queued for review."
            ],
            UpdatedAtUtc: now.AddMinutes(4));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-continuity-carry-forward-evidence-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [],
            Consequences: [],
            NextSessionCarryForward: carryForward);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithContinuitySignalLabelsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        WorkspaceChangePacketProjection continuityChange = new(
            PacketId: "packet-1",
            Kind: "next_session_carry_forward",
            Label: "Continuity carry-forward label",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(3));

        NextSessionCarryForwardProjection carryForward = new(
            CarryForwardId: "carry-1",
            Label: "Return handoff label",
            Summary: "",
            ReturnSummary: "",
            NextSafeAction: "",
            EvidenceLines: [],
            UpdatedAtUtc: now.AddMinutes(4));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [continuityChange],
            Consequences: [],
            NextSessionCarryForward: carryForward);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithContinuitySignalKindsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        WorkspaceChangePacketProjection continuityChange = new(
            PacketId: "packet-1",
            Kind: "next_session_carry_forward",
            Label: "",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(3));

        NextSessionCarryForwardProjection carryForward = new(
            CarryForwardId: "carry-1",
            Label: "",
            Summary: "",
            ReturnSummary: "",
            NextSafeAction: "",
            EvidenceLines: [],
            UpdatedAtUtc: now.AddMinutes(4));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [continuityChange],
            Consequences: [],
            NextSessionCarryForward: carryForward);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithDiscontinuityMentionsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        WorkspaceChangePacketProjection discontinuitySignal = new(
            PacketId: "packet-discontinuity-1",
            Kind: "status_note",
            Label: "Discontinuity watch note",
            Summary: "Discontinuity drift remains under review while queue triage is scheduled.",
            UpdatedAtUtc: now.AddMinutes(3));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-discontinuity-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [discontinuitySignal],
            Consequences: [],
            NextSessionCarryForward: null);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithJournalismKeynoteMentionsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        WorkspaceChangePacketProjection keynoteSignal = new(
            PacketId: "packet-journalism-keynote-1",
            Kind: "status_note",
            Label: "Journalism keynote status",
            Summary: "Keynote schedule remains stable while publication review is pending.",
            UpdatedAtUtc: now.AddMinutes(3));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-journalism-keynote-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [keynoteSignal],
            Consequences: [],
            NextSessionCarryForward: null);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithJournalEnterpriseMentionsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        WorkspaceChangePacketProjection enterpriseSignal = new(
            PacketId: "packet-journal-enterprise-1",
            Kind: "status_brief",
            Label: "Journal enterprise alignment",
            Summary: "Enterprise alignment remains stable while governance review is pending.",
            UpdatedAtUtc: now.AddMinutes(3));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-journal-enterprise-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [enterpriseSignal],
            Consequences: [],
            NextSessionCarryForward: null);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithJournalUpdateableMentionsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        WorkspaceChangePacketProjection updateableSignal = new(
            PacketId: "packet-journal-updateable-1",
            Kind: "status_brief",
            Label: "Journal updateable template",
            Summary: "Template policy remains stable while governance review is pending.",
            UpdatedAtUtc: now.AddMinutes(3));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-journal-updateable-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [updateableSignal],
            Consequences: [],
            NextSessionCarryForward: null);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithCampaignerReturnableWindowshadeMentionsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        WorkspaceChangePacketProjection windowshadeSignal = new(
            PacketId: "packet-campaigner-returnable-windowshade-1",
            Kind: "status_note",
            Label: "Campaigner returnable windowshade note",
            Summary: "Windowshade procurement remains scheduled for maintenance follow-through.",
            UpdatedAtUtc: now.AddMinutes(3));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-campaigner-returnable-windowshade-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [windowshadeSignal],
            Consequences: [],
            NextSessionCarryForward: null);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithContinuitySparseSignalKindsAndLabelsOnly()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        WorkspaceChangePacketProjection continuityChange = new(
            PacketId: "packet-1",
            Kind: "",
            Label: "Continuity carry-forward label",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(3));

        NextSessionCarryForwardProjection carryForward = new(
            CarryForwardId: "carry-1",
            Label: "Return handoff label",
            Summary: "",
            ReturnSummary: "",
            NextSafeAction: "",
            EvidenceLines: [],
            UpdatedAtUtc: now.AddMinutes(4));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [continuityChange],
            Consequences: [],
            NextSessionCarryForward: carryForward);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithContinuityRecapKindsOnly()
    {
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        PublicationSafeProjection recap = new(
            ProjectionId: "recap-1",
            Kind: "session_recap",
            Label: "",
            Summary: "");

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [recap],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [],
            Consequences: [],
            NextSessionCarryForward: null);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithContinuityRecapKindsAndVerboseCarryForward()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        PublicationSafeProjection recap = new(
            ProjectionId: "recap-1",
            Kind: "session_recap",
            Label: "",
            Summary: "");
        WorkspaceChangePacketProjection continuityChange = new(
            PacketId: "packet-1",
            Kind: "next_session_carry_forward",
            Label: "",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(2));
        NextSessionCarryForwardProjection carryForward = new(
            CarryForwardId: "carry-1",
            Label: "Continuity return lane",
            Summary: "Carry-forward continuity remains active for next session.",
            ReturnSummary: "Continuity handoff remains attached to governed return.",
            NextSafeAction: "Review continuity handoff before table start.",
            EvidenceLines: [],
            UpdatedAtUtc: now.AddMinutes(3));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [recap],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return lane summary",
            ChangePackets: [continuityChange],
            Consequences: [],
            NextSessionCarryForward: carryForward);
    }

    private static CampaignWorkspaceProjection BuildWorkspaceWithContinuityKindsAndVerboseRecapEvidence()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        PublicationSafeProjection recapA = new(
            ProjectionId: "recap-a",
            Kind: "session_recap",
            Label: "Session recap lane A",
            Summary: "Session recap evidence line A remains verbose while continuity projections hydrate.");
        PublicationSafeProjection recapB = new(
            ProjectionId: "recap-b",
            Kind: "session_recap",
            Label: "Session recap lane B",
            Summary: "Session recap evidence line B remains verbose while continuity projections hydrate.");
        PublicationSafeProjection recapC = new(
            ProjectionId: "recap-c",
            Kind: "session_recap",
            Label: "Session recap lane C",
            Summary: "Session recap evidence line C remains verbose while continuity projections hydrate.");
        WorkspaceChangePacketProjection continuityChange = new(
            PacketId: "packet-1",
            Kind: "next_session_carry_forward",
            Label: "",
            Summary: "",
            UpdatedAtUtc: now.AddMinutes(3));

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-a",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [recapA, recapB, recapC],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "",
            ChangePackets: [continuityChange],
            Consequences: [],
            NextSessionCarryForward: null);
    }

    private static WorkspaceRestoreProjection BuildRestoreWithTravelPacketSparseEvidence()
    {
        DateTimeOffset now = DateTimeOffset.Parse("2026-04-03T00:00:00Z");
        RuleEnvironmentRef sparseRuleEnvironment = new(
            EnvironmentId: "env-restore-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "",
            ApprovalState: "campaign_approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        ClaimedDeviceRestoreProjection device = new(
            InstallationId: "install-1",
            DeviceRole: "travel_cache",
            Platform: "linux",
            HeadId: "offline",
            Channel: "preview",
            HostLabel: null,
            RestoreSummary: "");

        RestoreArtifactProjection artifact = new(
            ArtifactId: "artifact-1",
            Label: "",
            Kind: "campaign_recap_bundle",
            Summary: "");

        return new WorkspaceRestoreProjection(
            RestoreId: "restore-sparse-travel-1",
            UserId: "user-1",
            RecentDossiers: [],
            RecentCampaigns: [],
            RecentRuleEnvironments: [sparseRuleEnvironment],
            RecentArtifacts: [artifact],
            Entitlements: [],
            ClaimedDevices: [device],
            ConflictSummaries: [],
            LocalOnlyNotes: [],
            GeneratedAtUtc: now);
    }

    private static ClaimedDeviceRestoreProjection BuildClaimedDeviceRestore(string deviceRole, string restoreSummary)
        => new(
            InstallationId: "install-claimed-1",
            DeviceRole: deviceRole,
            Platform: "linux",
            HeadId: "desktop",
            Channel: "preview",
            HostLabel: null,
            RestoreSummary: restoreSummary);

    private static WorkspaceRestoreProjection BuildEmptyRestore()
        => new(
            RestoreId: "restore-1",
            UserId: "user-1",
            RecentDossiers: [],
            RecentCampaigns: [],
            RecentRuleEnvironments: [],
            RecentArtifacts: [],
            Entitlements: [],
            ClaimedDevices: [],
            ConflictSummaries: [],
            LocalOnlyNotes: [],
            GeneratedAtUtc: DateTimeOffset.Parse("2026-04-03T00:00:00Z"));
}
