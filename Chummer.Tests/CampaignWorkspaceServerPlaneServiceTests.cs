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
