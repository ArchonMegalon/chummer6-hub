using Chummer.Campaign.Contracts;
using Chummer.Contracts.Receipts;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Contracts.Community;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class CampaignSpineServiceReceiptEnvelopeTests
{
    [Fact]
    public void RecordTravelPrefetch_emits_shared_campaign_receipt_envelope()
    {
        IConfiguration configuration = CreateConfiguration();
        CommunityStore store = new(configuration, NullLogger<CommunityStore>.Instance);
        CampaignSpineService service = new(
            store,
            new WorkspaceLifecyclePolicyService(configuration),
            new CampaignArtifactRegistryBridge(store));

        TravelPrefetchReceiptProjection receipt = service.RecordTravelPrefetch(
            user: new HubUserDto(
                UserId: "user-a",
                SubjectId: "sub-a",
                DisplayName: "Apex",
                Handle: "apex",
                Visibility: "private",
                Timezone: "UTC",
                CountryCode: "AT",
                LinkedPrincipals: [],
                GroupIds: [],
                CreatedAtUtc: DateTimeOffset.UtcNow,
                UpdatedAtUtc: DateTimeOffset.UtcNow),
            workspace: new CampaignWorkspaceProjection(
                WorkspaceId: "workspace-a",
                CampaignId: "campaign-a",
                CampaignName: "Neon Cradle",
                Visibility: "group",
                RuleEnvironment: new RuleEnvironmentRef("env-a", "campaign", "sr5-core", "approved", [], [], []),
                Crews: [],
                Dossiers: [],
                Runs: [],
                RecapShelf: [],
                ReadinessCues: [],
                LatestContinuity: null,
                ReturnSummary: "Return to the active runboard."),
            device: new ClaimedDeviceRestoreProjection(
                InstallationId: "install-a",
                DeviceRole: "travel",
                Platform: "desktop",
                HeadId: "head-a",
                Channel: "stable",
                HostLabel: "Rig",
                RestoreSummary: "Ready"),
            prefetchSummary: "Prefetch the offline continuity package.",
            inventoryLines: ["Package present."],
            boundaries: ["Offline cache only."],
            note: "Bounded test");

        Assert.NotNull(receipt.Envelope);
        Assert.Equal(ReceiptProvenanceClasses.Runtime, receipt.Envelope!.ProvenanceClass);
        Assert.Equal(ReceiptExposureClasses.SignedIn, receipt.Envelope.ExposureClass);
        Assert.Equal(ReceiptLifecycleStates.Verified, receipt.Envelope.LifecycleState);
        Assert.Equal("campaign.workspace", receipt.Envelope.OwnerScope);
        Assert.Equal("travel_prefetch", receipt.Envelope.ReceiptKind);
        Assert.Equal(receipt.ReceiptId, receipt.Envelope.EvidenceRef);
    }

    [Fact]
    public void Campaign_spine_service_routes_campaign_consequence_receipts_through_shared_helper()
    {
        string repoRoot = Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "../../../../../"));
        string source = File.ReadAllText(Path.Combine(
            repoRoot,
            "Chummer.Run.Api/Services/Community/CampaignSpineService.cs"));

        Assert.Contains("private static CampaignConsequenceReceipt CampaignConsequence(", source, StringComparison.Ordinal);
        Assert.DoesNotContain("new CampaignConsequenceReceipt(", source, StringComparison.Ordinal);
    }

    private static IConfiguration CreateConfiguration()
    {
        string root = Path.Combine(Path.GetTempPath(), "chummer-campaign-envelope-tests", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        return new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_COMMUNITY_STORE_PATH"] = Path.Combine(root, "community.json")
            })
            .Build();
    }
}
