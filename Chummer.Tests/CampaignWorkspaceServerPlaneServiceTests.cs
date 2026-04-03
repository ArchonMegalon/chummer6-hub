using Chummer.Campaign.Contracts;
using System.Reflection;
using Chummer.Run.Api.Contracts;
using Chummer.Run.Api.Services.Community;
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
        Assert.Contains("control", tokens);
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
        Assert.Contains("contacts", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains("heat", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
        Assert.Contains("return", packet.SearchTerms, StringComparer.OrdinalIgnoreCase);
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

    private static IReadOnlyList<GovernedPrepPacketSummary> InvokeBuildPrepPackets(
        CampaignWorkspaceProjection workspace,
        WorkspaceRestoreProjection restore)
    {
        MethodInfo method = typeof(CampaignWorkspaceServerPlaneService)
            .GetMethod("BuildPrepPackets", BindingFlags.NonPublic | BindingFlags.Static)
            ?? throw new InvalidOperationException("BuildPrepPackets was not found.");

        return Assert.IsAssignableFrom<IReadOnlyList<GovernedPrepPacketSummary>>(method.Invoke(null, [workspace, restore, null]));
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
