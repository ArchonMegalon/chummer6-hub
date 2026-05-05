using Chummer.Campaign.Contracts;
using Chummer.Run.Api.Contracts;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.Services.Support;
using Chummer.Run.Contracts.Community;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class CampaignMovementServiceTests
{
    [Fact]
    public void MoveDossierPersistsTargetEventOwnershipAndAuditReceipts()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), "campaign-movement-service", Guid.NewGuid().ToString("N"));
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
            GroupService groups = new(store, accounts);
            SupportStore supportStore = new(configuration, NullLogger<SupportStore>.Instance);
            CampaignSpineService campaignSpine = new(
                store,
                new WorkspaceLifecyclePolicyService(configuration),
                new CampaignArtifactRegistryBridge(store),
                supportStore);

            var operatorUser = accounts.EnsureUser("subject.demo", "Demo Operator", "demo@example.invalid");
            var sourceWorkspace = campaignSpine.GetStarterWorkspace(operatorUser)
                ?? throw new InvalidOperationException("Expected a starter workspace.");
            var sourceDossier = campaignSpine.GetAccountSummary(operatorUser).Dossiers.First();
            var targetOwner = accounts.EnsureUser("subject.outsider", "Outsider Demo", "outsider@example.invalid");
            var targetGroup = groups.CreateGroup(new CreateGroupRequest(
                SubjectId: operatorUser.SubjectId,
                Name: "Thursday Crew Relay",
                GroupType: "campaign",
                Visibility: "group",
                Capabilities: null));
            var targetCampaign = groups.GetOrCreateCampaign(targetGroup.GroupId, "hub", "Thursday Crew Relay");

            DossierMovementPlannerProjection? movementPlan = campaignSpine.GetDossierMovementPlan(operatorUser, sourceWorkspace.WorkspaceId);
            Assert.NotNull(movementPlan);
            Assert.Contains(
                movementPlan!.TargetGroups,
                item => string.Equals(item.GroupId, targetGroup.GroupId, StringComparison.OrdinalIgnoreCase)
                    && item.CampaignOptions.Any(option => string.Equals(option.CampaignId, targetCampaign.CampaignId, StringComparison.OrdinalIgnoreCase)));

            DossierMovementReceiptProjection movement = campaignSpine.MoveDossier(operatorUser, new DossierMovementRequest(
                DossierId: sourceDossier.DossierId,
                TargetGroupId: targetGroup.GroupId,
                TargetCampaignId: targetCampaign.CampaignId,
                TargetCampaignTitle: targetCampaign.Title,
                TargetRunTitle: "Dockside handoff",
                TargetSceneTitle: "Pier 3 exchange",
                TargetOwnerUserId: targetOwner.UserId,
                Note: "GM handoff for the next run."));

            Assert.True(movement.GroupChanged);
            Assert.True(movement.CampaignChanged);
            Assert.True(movement.OwnershipChanged);
            Assert.True(movement.EventChanged);
            Assert.Equal("Dockside handoff", movement.TargetRunTitle);
            Assert.Equal("Pier 3 exchange", movement.TargetSceneTitle);
            Assert.Contains(movement.TransferReceipt.Receipts, item => string.Equals(item.SourceKind, "target_run", StringComparison.OrdinalIgnoreCase));
            Assert.Contains(movement.TransferReceipt.Receipts, item => string.Equals(item.SourceKind, "target_scene", StringComparison.OrdinalIgnoreCase));
            Assert.Contains(movement.AuditLines, line => line.Contains("Dockside handoff", StringComparison.OrdinalIgnoreCase));
            Assert.Contains(movement.AuditLines, line => line.Contains("Pier 3 exchange", StringComparison.OrdinalIgnoreCase));

            var targetWorkspace = campaignSpine.GetAccountSummary(targetOwner).Workspaces
                .First(item => string.Equals(item.CampaignId, targetCampaign.CampaignId, StringComparison.OrdinalIgnoreCase));
            Assert.Contains(
                targetWorkspace.Dossiers,
                item => string.Equals(item.DossierId, sourceDossier.DossierId, StringComparison.OrdinalIgnoreCase)
                    && string.Equals(item.CurrentRunId, movement.TargetRunId, StringComparison.OrdinalIgnoreCase)
                    && string.Equals(item.CurrentSceneId, movement.TargetSceneId, StringComparison.OrdinalIgnoreCase));

            IReadOnlyList<DossierMovementReceiptProjection> workspaceReceipts = campaignSpine.GetDossierMovements(operatorUser, targetWorkspace.WorkspaceId);
            Assert.Contains(workspaceReceipts, item => string.Equals(item.MovementId, movement.MovementId, StringComparison.OrdinalIgnoreCase));
            IReadOnlyList<DossierMovementReceiptProjection> targetOwnerReceipts = campaignSpine.GetDossierMovements(targetOwner, targetWorkspace.WorkspaceId);
            Assert.Contains(targetOwnerReceipts, item => string.Equals(item.MovementId, movement.MovementId, StringComparison.OrdinalIgnoreCase));

            var relayGroup = groups.CreateGroup(new CreateGroupRequest(
                SubjectId: operatorUser.SubjectId,
                Name: "Saturday Relay Crew",
                GroupType: "campaign",
                Visibility: "group",
                Capabilities: null));
            var relayCampaign = groups.GetOrCreateCampaign(relayGroup.GroupId, "hub", "Saturday Relay Crew");

            RosterTransferProjection returnTransfer = campaignSpine.TransferRoster(operatorUser, new RosterTransferRequest(
                DossierId: sourceDossier.DossierId,
                TargetGroupId: relayGroup.GroupId,
                TargetCampaignId: relayCampaign.CampaignId,
                TargetCampaignTitle: relayCampaign.Title,
                TargetOwnerUserId: targetOwner.UserId,
                Note: "Second relay after the handoff."));
            Assert.Contains(returnTransfer.Receipts, item => string.Equals(item.SourceKind, "target_run", StringComparison.OrdinalIgnoreCase));

            CommunityStore reloadedStore = new(configuration, NullLogger<CommunityStore>.Instance);
            SupportStore reloadedSupportStore = new(configuration, NullLogger<SupportStore>.Instance);
            CampaignSpineService reloadedSpine = new(
                reloadedStore,
                new WorkspaceLifecyclePolicyService(configuration),
                new CampaignArtifactRegistryBridge(reloadedStore),
                reloadedSupportStore);
            IReadOnlyList<DossierMovementReceiptProjection> reloadedReceipts = reloadedSpine.GetDossierMovements(operatorUser, targetWorkspace.WorkspaceId);
            Assert.True(reloadedReceipts.Count >= 2);
            Assert.Contains(reloadedReceipts, item => string.Equals(item.MovementId, movement.MovementId, StringComparison.OrdinalIgnoreCase));
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
