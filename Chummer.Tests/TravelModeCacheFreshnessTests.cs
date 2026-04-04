using Chummer.Campaign.Contracts;
using Chummer.Run.Api.Contracts;
using Chummer.Run.Api.Services.Community;
using System.Reflection;
using Xunit;

namespace Chummer.Tests;

public sealed class TravelModeCacheFreshnessTests
{
    [Fact]
    public void BuildTravelMode_ReportsFreshAndStaleCacheCountsFromPrefetchReceiptRecency()
    {
        DateTimeOffset now = DateTimeOffset.UtcNow;
        CampaignWorkspaceProjection workspace = BuildWorkspace(
            new TravelPrefetchReceiptProjection(
                ReceiptId: "receipt-fresh",
                WorkspaceId: "workspace-1",
                CampaignId: "campaign-1",
                InstallationId: "install-fresh",
                DeviceRole: "travel_cache",
                Platform: "ios",
                HeadId: "mobile",
                Channel: "stable",
                PrefetchSummary: "Fresh staged receipt.",
                InventoryLines: [],
                Boundaries: [],
                InitiatedByUserId: "user-1",
                StagedAtUtc: now.AddDays(-2)),
            new TravelPrefetchReceiptProjection(
                ReceiptId: "receipt-stale",
                WorkspaceId: "workspace-1",
                CampaignId: "campaign-1",
                InstallationId: "install-stale",
                DeviceRole: "travel_cache",
                Platform: "android",
                HeadId: "mobile",
                Channel: "stable",
                PrefetchSummary: "Old staged receipt.",
                InventoryLines: [],
                Boundaries: [],
                InitiatedByUserId: "user-1",
                StagedAtUtc: now.AddDays(-21)));

        WorkspaceRestoreProjection restore = BuildRestore(
            new ClaimedDeviceRestoreProjection(
                InstallationId: "install-fresh",
                DeviceRole: "travel_cache",
                Platform: "ios",
                HeadId: "mobile",
                Channel: "stable",
                HostLabel: "tablet",
                RestoreSummary: "Bounded offline use is staged."),
            new ClaimedDeviceRestoreProjection(
                InstallationId: "install-stale",
                DeviceRole: "travel_cache",
                Platform: "android",
                HeadId: "mobile",
                Channel: "stable",
                HostLabel: "phone",
                RestoreSummary: "Bounded offline use is staged."));

        TravelModeReadinessSummary summary = InvokeBuildTravelMode(workspace, restore, BuildPrepLibrary());

        Assert.Equal(2, summary.TravelReadyDeviceCount);
        Assert.Equal(1, summary.FreshCacheDeviceCount);
        Assert.Equal(1, summary.StaleCacheDeviceCount);
        Assert.Contains("fresh staged cache", summary.CacheFreshnessSummary, StringComparison.Ordinal);
        Assert.Contains("while offline", summary.OfflineActionabilitySummary, StringComparison.Ordinal);
        Assert.Contains("downtime/diary", summary.OfflineActionabilitySummary, StringComparison.Ordinal);
        Assert.Equal("ready", summary.Devices.First(item => item.InstallationId == "install-fresh").Status);
        Assert.Equal("stale", summary.Devices.First(item => item.InstallationId == "install-stale").Status);
    }

    [Fact]
    public void BuildTravelMode_ReportsStaleFreshnessWhenNoPrefetchReceiptExistsYet()
    {
        CampaignWorkspaceProjection workspace = BuildWorkspace();
        WorkspaceRestoreProjection restore = BuildRestore(
            new ClaimedDeviceRestoreProjection(
                InstallationId: "install-a",
                DeviceRole: "travel_cache",
                Platform: "windows",
                HeadId: "avalonia",
                Channel: "preview",
                HostLabel: "workstation",
                RestoreSummary: "Bounded offline use is staged."));

        TravelModeReadinessSummary summary = InvokeBuildTravelMode(workspace, restore, BuildPrepLibrary());

        Assert.Equal(1, summary.TravelReadyDeviceCount);
        Assert.Equal(0, summary.FreshCacheDeviceCount);
        Assert.Equal(1, summary.StaleCacheDeviceCount);
        Assert.Contains("No travel-prefetch receipt exists yet", summary.CacheFreshnessSummary, StringComparison.Ordinal);
        Assert.Contains("while offline", summary.OfflineActionabilitySummary, StringComparison.Ordinal);
        Assert.Equal("stale", summary.Devices.Single().Status);
    }

    private static TravelModeReadinessSummary InvokeBuildTravelMode(
        CampaignWorkspaceProjection workspace,
        WorkspaceRestoreProjection restore,
        CampaignPrepLibrarySummary prepLibrary)
    {
        MethodInfo method = typeof(CampaignWorkspaceServerPlaneService)
            .GetMethod("BuildTravelMode", BindingFlags.NonPublic | BindingFlags.Static)
            ?? throw new InvalidOperationException("BuildTravelMode was not found.");

        return Assert.IsType<TravelModeReadinessSummary>(method.Invoke(null, [workspace, restore, prepLibrary]));
    }

    private static CampaignPrepLibrarySummary BuildPrepLibrary()
        => new(
            Summary: "Prep packets are governed.",
            BindingSummary: "Bound to campaign truth.",
            SearchSummary: "Search is active.",
            ReusablePacketCount: 0,
            SearchablePacketCount: 0,
            Packets: []);

    private static WorkspaceRestoreProjection BuildRestore(params ClaimedDeviceRestoreProjection[] devices)
        => new(
            RestoreId: "restore-1",
            UserId: "user-1",
            RecentDossiers: [],
            RecentCampaigns: [],
            RecentRuleEnvironments: [],
            RecentArtifacts: [],
            Entitlements: [],
            ClaimedDevices: devices,
            ConflictSummaries: [],
            LocalOnlyNotes: [],
            GeneratedAtUtc: DateTimeOffset.UtcNow);

    private static CampaignWorkspaceProjection BuildWorkspace(params TravelPrefetchReceiptProjection[] receipts)
    {
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr6-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr6-core"],
            HouseRulePacks: [],
            OptionToggles: []);

        return new CampaignWorkspaceProjection(
            WorkspaceId: "workspace-1",
            CampaignId: "campaign-1",
            CampaignName: "Neon Cradle",
            Visibility: "group",
            RuleEnvironment: environment,
            Crews: [],
            Dossiers: [],
            Runs: [],
            RecapShelf: [],
            ReadinessCues: [],
            LatestContinuity: null,
            ReturnSummary: "Return stays governed.",
            TravelPrefetches: receipts);
    }
}
