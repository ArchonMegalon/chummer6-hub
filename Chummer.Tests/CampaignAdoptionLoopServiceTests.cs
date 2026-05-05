using Chummer.Campaign.Contracts;
using Chummer.Run.Api.Contracts;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.Services.Support;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class CampaignAdoptionLoopServiceTests
{
    [Fact]
    public void CampaignAdoptionLoopPersistsGoalsWorldTickAndApprovedResolutionReport()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), "campaign-adoption-loop-service", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempRoot);

        try
        {
            IConfiguration configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_COMMUNITY_STORE_PATH"] = Path.Combine(tempRoot, "community-store.json"),
                    ["CHUMMER_WORKSPACE_RESTORE_RETENTION_DAYS"] = "30"
                })
                .Build();

            CommunityStore store = new(configuration, NullLogger<CommunityStore>.Instance);
            AccountService accounts = new(store);
            SupportStore supportStore = new(configuration, NullLogger<SupportStore>.Instance);
            CampaignSpineService campaignSpine = new(
                store,
                new WorkspaceLifecyclePolicyService(configuration),
                new CampaignArtifactRegistryBridge(store),
                supportStore);

            var user = accounts.EnsureUser("subject.demo", "Demo Operator", "demo@example.invalid");
            var workspace = campaignSpine.GetStarterWorkspace(user)
                ?? throw new InvalidOperationException("Expected a starter workspace.");
            var run = workspace.Runs.First();
            var dossier = workspace.Dossiers.First();

            campaignSpine.UpsertRunboardContinuity(user, workspace, new RunboardContinuityUpdateRequest(
                RunId: run.RunId,
                ActiveSceneId: run.ActiveSceneId,
                TurnLedgerSummary: "Minor-action handoff stays pinned before the next opposition pass.",
                TurnLedgerEvidenceLines:
                [
                    "Player lane confirmed the last spend on the governed turn ledger.",
                    "Hub persisted the same handoff without replaying engine math."
                ],
                RunboardStateSummary: "Two blockers and the same extraction objective stay pinned on the GM runboard.",
                ObjectiveLines:
                [
                    "Extract the courier without spiking public awareness.",
                    "Keep the matrix relay stable until exfiltration."
                ],
                Blockers:
                [
                    "Suppress the loading-dock mooks before the next pass.",
                    "Resolve overwatch pressure before the courier leaves the van."
                ],
                ResolutionReportStatus: "draft",
                ResolutionReportSummary: "ResolutionReport draft keeps the courier handoff and matrix fallout continuity on one hub lane.",
                ResolutionNotes:
                [
                    "Spoiler-safe notes stay bounded to the same closeout draft.",
                    "No VTT map state or engine math is owned by hub here."
                ],
                NextSafeAction: "Open ResolutionReport and keep the same return lane on /account/work#runboard.",
                Note: "Campaign adoption loop test setup."));

            campaignSpine.UpsertCampaignAdoption(user, workspace, new CampaignAdoptionUpdateRequest(
                SafeToPlay: true,
                ConfidencePercent: 82,
                RunnerCount: workspace.Dossiers.Count,
                ActiveJobCount: 1,
                ContactCount: 3,
                HouseRuleCount: workspace.RuleEnvironment.HouseRulePacks.Count,
                ExplicitUnknowns:
                [
                    "Two legacy contact modifiers still need manual provenance review."
                ],
                RecommendedNextActions:
                [
                    "Keep future changes only and preserve legacy notes on the governed return lane."
                ],
                Summary: "Campaign adoption wizard says this workspace is safe to play while unknown provenance stays explicit.",
                NextSafeAction: "Review the adoption wizard on /account/work#adoption before you reopen the next campaign return.",
                Note: "Campaign adoption loop service proof."));

            RunnerGoalProjection goal = campaignSpine.UpsertRunnerGoal(user, workspace, new RunnerGoalUpdateRequest(
                DossierId: dossier.DossierId,
                Label: "Delta-grade wired reflexes fund",
                TargetKind: "upgrade_fund",
                TargetReference: "wired_reflexes_delta",
                SavedNuyen: 18500,
                NuyenRequired: 217000,
                KarmaReserved: 12,
                DowntimeDays: 4,
                ApprovalStatus: "gm_review",
                NextSafeAction: "Review runner goal pins on /account/work#runner-goals before you close the next ResolutionReport.",
                Note: "Campaign adoption loop service proof."));

            ResolutionReportApprovalProjection approval = campaignSpine.ApproveResolutionReport(user, workspace, new ResolutionReportApprovalRequest(
                RunId: run.RunId,
                Summary: "ResolutionReport approval closes the courier extraction on the governed hub lane.",
                WorldTickSummary: "Dockside courier fallout becomes the first BLACK LEDGER WorldTick for Tacoma.",
                ConsequenceSummary: "Heat escalates across Tacoma after the courier extraction closes out.",
                NewsTitle: "Tacoma grid rumor points to a vanished courier",
                NewsSummary: "Player-safe reports say a courier vanished after a dockside outage, but the source stays preview-only.",
                NewsSource: "Tacoma Shadowfeed",
                NewsUrl: "https://example.invalid/news/tacoma-courier-rumor",
                NextSafeAction: "Review the first WorldTick and player-safe news item on /account/work#campaign-memory before you reopen the runboard.",
                Note: "Campaign adoption loop service proof."));

            Assert.Equal(run.RunId, approval.RunId);
            Assert.Equal(goal.GoalId, campaignSpine.GetCampaignAdoptionLoop(user, workspace.WorkspaceId)?.RunnerGoals.First().GoalId);

            CommunityStore reloadedStore = new(configuration, NullLogger<CommunityStore>.Instance);
            SupportStore reloadedSupportStore = new(configuration, NullLogger<SupportStore>.Instance);
            CampaignSpineService reloadedSpine = new(
                reloadedStore,
                new WorkspaceLifecyclePolicyService(configuration),
                new CampaignArtifactRegistryBridge(reloadedStore),
                reloadedSupportStore);

            CampaignAdoptionLoopProjection reloadedLoop = reloadedSpine.GetCampaignAdoptionLoop(user, workspace.WorkspaceId)
                ?? throw new InvalidOperationException("Expected the campaign adoption loop after reload.");
            Assert.NotNull(reloadedLoop.Adoption);
            Assert.True(reloadedLoop.Adoption!.SafeToPlay);
            Assert.Equal(82, reloadedLoop.Adoption.ConfidencePercent);
            Assert.Contains(reloadedLoop.RunnerGoals, item => string.Equals(item.GoalId, goal.GoalId, StringComparison.OrdinalIgnoreCase));
            Assert.NotNull(reloadedLoop.ResolutionReportApproval);
            Assert.Contains(reloadedLoop.WorldTicks, item => item.Summary.Contains("BLACK LEDGER WorldTick", StringComparison.Ordinal));
            Assert.Contains(reloadedLoop.PlayerSafeNews, item => item.Title.Contains("Tacoma grid rumor", StringComparison.Ordinal));

            CampaignWorkspaceProjection reloadedWorkspace = reloadedSpine.GetWorkspace(user, workspace.WorkspaceId)
                ?? throw new InvalidOperationException("Expected the workspace after reload.");
            Assert.NotNull(reloadedWorkspace.CampaignAdoptionLoop);
            Assert.Contains(reloadedWorkspace.ChangePackets ?? Array.Empty<WorkspaceChangePacketProjection>(), item => string.Equals(item.Kind, "player_safe_news", StringComparison.Ordinal));
            Assert.Contains(reloadedWorkspace.RecapShelf, item => string.Equals(item.Kind, "player_safe_news", StringComparison.Ordinal));
        }
        finally
        {
            if (Directory.Exists(tempRoot))
            {
                Directory.Delete(tempRoot, recursive: true);
            }
        }
    }
}
