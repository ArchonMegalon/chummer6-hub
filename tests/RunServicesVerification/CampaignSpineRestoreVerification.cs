using System.IO;
using System.Net.Http;
using System.Net.Http.Json;
using System.Reflection;
using System.Threading;
using Chummer.Campaign.Contracts;
using Chummer.Control.Contracts.Support;
using Chummer.Run.Api.Contracts;
using Chummer.Run.Api.Services.Support;
using Chummer.Run.Api.ViewModels;
using Chummer.Hub.Registry.Contracts.InstallLinking;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Contracts.Community;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;

namespace RunServicesVerification;

internal static class CampaignSpineRestoreVerification
{
    public static Task RunAsync()
    {
        VerifyClaimedDeviceRestoreSummariesNameExactPrefetchSet();
        VerifyRestoreConflictReceiptsCaptureStaleClaimAndEntitlementState();
        VerifyRestoreConflictReceiptsCaptureDuplicateEntitlementReplication();
        VerifyServerPlaneProvenanceReceiptsExposeRecoveryPosture();
        VerifyServerPlanePrioritizesRecoverableProvenanceReceipts();
        VerifyServerPlaneNextSafeActionSurfacesRecoverableProvenance();
        VerifyServerPlaneRestoreReceiptStatusSummarizesBlockingRecovery();
        VerifyServerPlaneRestoreReceiptStatusFallsBackToRecoverableProvenanceLead();
        VerifyRestoreReceiptStatusEmitsTypedRecoveryActions();
        VerifyEntitlementSyncReceiptStatusUsesStandaloneScopeDefaults();
        VerifyEntitlementSyncProjectionStaysExplicitAndRecoverable();
        VerifyRestoreReceiptSurfaceProjectionCountsStayExplicit();
        VerifyRestoreReceiptSurfaceBreakdownsStayExplicitAndRecoverable();
        VerifyServerPlaneProvenanceReceiptsRecoverBlankIdentityFields();
        VerifyServerPlaneConflictReceiptsRecoverBlankSummaries();
        VerifyServerPlaneConflictReceiptsRecoverBlankIdentityFields();
        VerifyServerPlaneBlankArtifactDriftConflictsRecoverDownloadResolution();
        VerifyServerPlaneBlockingSeverityControlsContinuePosture();
        VerifyServerPlanePrioritizesReceiptBackedConflictsOverSummaryOverflow();
        VerifyServerPlanePrioritizesRecoverableConflictReceipts();
        VerifyServerPlaneActionsRecoverBlankBlockingConflictResolutions();
        VerifyRestoreReceiptsSurviveCommunityStoreReload();
        VerifyAftermathArtifactMetadataSurvivesReload();
        return Task.CompletedTask;
    }

    private static void VerifyRestoreReceiptSurfaceProjectionCountsStayExplicit()
    {
        MethodInfo buildMethod = typeof(CampaignWorkspaceServerPlaneService).GetMethod(
            "BuildRestoreReceiptSurfaceProjections",
            BindingFlags.NonPublic | BindingFlags.Static)
            ?? throw new InvalidOperationException("Expected restore receipt surface projection builder.");

        DateTimeOffset now = DateTimeOffset.UtcNow;
        IReadOnlyList<WorkspaceRestoreProvenanceReceipt> provenanceReceipts =
        [
            new(
                ReceiptId: "workspace-current-receipt",
                Kind: "restore_inventory_snapshot",
                SubjectId: "workspace-restore",
                Surface: "workspace_restore",
                Summary: "Workspace restore inventory is current.",
                Proof: "workspace-inventory",
                ObservedAtUtc: now),
            new(
                ReceiptId: "entitlement-drift-receipt",
                Kind: "entitlement_artifact_drift",
                SubjectId: "artifact-preview-linux",
                Surface: "entitlement_sync",
                Summary: "Entitlement replay points at a stale release artifact.",
                Proof: "artifact-preview-linux",
                ObservedAtUtc: now)
        ];
        IReadOnlyList<WorkspaceRestoreProvenanceRecoveryProjection> provenanceRecoveryReceipts =
        [
            new(
                ReceiptId: "workspace-current-receipt",
                Kind: "restore_inventory_snapshot",
                SubjectId: "workspace-restore",
                Surface: "workspace_restore",
                Summary: "Workspace restore inventory is current.",
                Proof: "workspace-inventory",
                ObservedAtUtc: now,
                Authority: "hub_campaign_spine_projection",
                StalenessPosture: "current_receipt",
                RecoverabilityPosture: "recoverable_with_receipt",
                RecoveryHint: "Open the restore rail and review this workspace receipt before editing shared campaign state on another device.",
                RecoveryRoute: "/account/work",
                RecoverySummary: "Receipt for workspace-restore is recoverable through /account/work if restore evidence drifts.",
                ContinuePosture: "safe_to_continue_with_receipt"),
            new(
                ReceiptId: "entitlement-drift-receipt",
                Kind: "entitlement_artifact_drift",
                SubjectId: "artifact-preview-linux",
                Surface: "entitlement_sync",
                Summary: "Entitlement replay points at a stale release artifact.",
                Proof: "artifact-preview-linux",
                ObservedAtUtc: now,
                Authority: "hub_registry_release_receipts",
                StalenessPosture: "artifact_drift",
                RecoverabilityPosture: "recoverable_by_refresh",
                RecoveryHint: "Refresh the signed-in install rail so this artifact receipt matches the device before continuing.",
                RecoveryRoute: "/downloads",
                RecoverySummary: "Refresh artifact-preview-linux through /downloads before continuing from this restored workspace.",
                ContinuePosture: "refresh_before_continue")
        ];
        IReadOnlyList<WorkspaceRestoreConflictReceiptProjection> conflictReceipts = Array.Empty<WorkspaceRestoreConflictReceiptProjection>();

        IReadOnlyList<WorkspaceRestoreReceiptSurfaceProjection> projections =
            buildMethod.Invoke(
                null,
                [provenanceReceipts, provenanceRecoveryReceipts, conflictReceipts, new[] { "workspace_restore", "entitlement_sync" }]) as IReadOnlyList<WorkspaceRestoreReceiptSurfaceProjection>
            ?? throw new InvalidOperationException("Expected restore receipt surface projections.");

        VerificationAssert.True(
            projections.Count == 2
                && projections.Any(item =>
                    string.Equals(item.Surface, "workspace_restore", StringComparison.Ordinal)
                    && item.Status.SafeToContinueWithReceiptCount == 1
                    && string.Equals(item.Status.RecoveryRoute, "/account/work", StringComparison.Ordinal)
                    && string.Equals(item.Status.ContinuePosture, "safe_to_continue_with_receipt", StringComparison.Ordinal))
                && projections.Any(item =>
                    string.Equals(item.Surface, "entitlement_sync", StringComparison.Ordinal)
                    && item.Status.RefreshBeforeContinueCount == 1
                    && string.Equals(item.Status.RecoveryRoute, "/downloads", StringComparison.Ordinal)
                    && string.Equals(item.Status.ContinuePosture, "refresh_before_continue", StringComparison.Ordinal)),
            "Restore receipt surface projections should keep explicit safe-to-continue and refresh-before-continue counts per surface.");
    }

    private static void VerifyRestoreReceiptSurfaceBreakdownsStayExplicitAndRecoverable()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), "run-services-verification", "campaign-spine-restore-surface-breakdown", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempRoot);

        try
        {
            IConfiguration configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_COMMUNITY_STORE_PATH"] = Path.Combine(tempRoot, "community-store.json"),
                    ["CHUMMER_SUPPORT_STORE_PATH"] = Path.Combine(tempRoot, "support-store.json"),
                    ["CHUMMER_SUPPORT_PROGRESS_EMAIL_ENABLED"] = "false",
                    ["CHUMMER_WORKSPACE_RESTORE_RETENTION_DAYS"] = "30"
                })
                .Build();

            CommunityStore store = new(configuration, NullLogger<CommunityStore>.Instance);
            AccountService accounts = new(store);
            RewardService rewards = new(store);
            WorkspaceLifecyclePolicyService lifecycle = new(configuration);
            CampaignSpineService campaignSpine = new(store, lifecycle, new CampaignArtifactRegistryBridge(store));
            SupportStore supportStore = new(configuration, NullLogger<SupportStore>.Instance);
            SupportProgressEmailWorkflowService progressEmails = new(
                new HttpClient(new DisabledEmailHandler()),
                configuration,
                NullLogger<SupportProgressEmailWorkflowService>.Instance);
            CampaignWorkspaceServerPlaneService workspaceServerPlane = new(
                campaignSpine,
                new SupportCaseService(
                    supportStore,
                    new SupportAttachmentStorageService(configuration),
                    rewards,
                    progressEmails,
                    NullLogger<SupportCaseService>.Instance),
                new SupportCasePresentationService());

            HubUserDto user = accounts.EnsureUser("subject.restore.surface", "Surface Restore", "restore-surface@example.invalid");
            CampaignWorkspaceProjection workspace = campaignSpine.GetStarterWorkspace(user)
                ?? throw new InvalidOperationException("Expected a starter workspace.");
            DateTimeOffset now = DateTimeOffset.UtcNow;

            WorkspaceRestoreProjection restore = new(
                RestoreId: "restore-surface-breakdown",
                UserId: user.UserId,
                RecentDossiers: [],
                RecentCampaigns: [],
                RecentRuleEnvironments: [],
                RecentArtifacts: [],
                Entitlements: [],
                ClaimedDevices: [],
                ConflictSummaries: [],
                LocalOnlyNotes: [],
                GeneratedAtUtc: now,
                ProvenanceReceipts:
                [
                    new WorkspaceRestoreProvenanceReceipt(
                        ReceiptId: "workspace-current-receipt",
                        Kind: "restore_inventory_snapshot",
                        SubjectId: workspace.WorkspaceId,
                        Surface: "workspace_restore",
                        Summary: "Workspace restore inventory is current.",
                        Proof: "workspace-inventory",
                        ObservedAtUtc: now.AddMinutes(2)),
                    new WorkspaceRestoreProvenanceReceipt(
                        ReceiptId: "entitlement-drift-receipt",
                        Kind: "entitlement_artifact_drift",
                        SubjectId: "artifact-preview-linux",
                        Surface: "entitlement_sync",
                        Summary: "Entitlement replay points at a stale release artifact.",
                        Proof: "artifact-preview-linux",
                        ObservedAtUtc: now.AddMinutes(1))
                ],
                ConflictReceipts:
                [
                    new WorkspaceRestoreConflictReceipt(
                        ReceiptId: "entitlement-duplicate-grant",
                        Severity: "blocking",
                        Kind: "entitlement_replication_duplicate_grant",
                        SubjectId: "grant-preview-linux",
                        Summary: "Duplicate entitlement grant receipts are active for this install.",
                        Resolution: null,
                        ObservedAtUtc: now,
                        Surface: "entitlement_sync",
                        BlocksContinue: true)
                ]);

            lock (store.Gate)
            {
                store.RestoreByUserId[user.UserId] = restore;
                store.PersistLocked();
            }

            CampaignWorkspaceServerPlaneProjection serverPlane = workspaceServerPlane.GetWorkspaceServerPlane(user, workspace.WorkspaceId)
                ?? throw new InvalidOperationException("Expected workspace server plane.");
            EntitlementSyncReceiptProjection entitlementProjection = workspaceServerPlane.GetEntitlementSyncReceiptProjection(user);

            VerificationAssert.True(
                serverPlane.RestoreReceiptSurfaces.Count == 2
                    && serverPlane.RestoreReceiptSurfaces.Any(item =>
                        string.Equals(item.Surface, "workspace_restore", StringComparison.Ordinal)
                        && !string.IsNullOrWhiteSpace(item.Status.LeadReceiptId)
                        && !string.IsNullOrWhiteSpace(item.Status.LeadRecoveryHint)
                        && string.Equals(item.Status.RecoveryRoute, "/account/work", StringComparison.Ordinal)
                        && string.Equals(item.Status.ContinuePosture, "safe_to_continue_with_receipt", StringComparison.Ordinal))
                    && serverPlane.RestoreReceiptSurfaces.Any(item =>
                        string.Equals(item.Surface, "entitlement_sync", StringComparison.Ordinal)
                        && !string.IsNullOrWhiteSpace(item.Status.LeadReceiptId)
                        && item.Status.LeadRecoveryHint.Contains("account access", StringComparison.OrdinalIgnoreCase)
                        && string.Equals(item.Status.RecoveryRoute, "/account/access", StringComparison.Ordinal)
                        && string.Equals(item.Status.ContinuePosture, "review_before_continue", StringComparison.Ordinal)),
                "Workspace server plane should emit explicit per-surface receipt posture for workspace restore provenance and entitlement-sync conflict recovery.");
            VerificationAssert.True(
                entitlementProjection.ReceiptSurfaces.Count == 1
                    && string.Equals(entitlementProjection.ReceiptSurfaces[0].Surface, "entitlement_sync", StringComparison.Ordinal)
                    && string.Equals(entitlementProjection.ReceiptSurfaces[0].Status.LeadReceiptId, entitlementProjection.ReceiptStatus.LeadReceiptId, StringComparison.Ordinal)
                    && !string.IsNullOrWhiteSpace(entitlementProjection.ReceiptSurfaces[0].Status.LeadRecoveryHint)
                    && string.Equals(entitlementProjection.ReceiptSurfaces[0].Status.ContinuePosture, entitlementProjection.ReceiptStatus.ContinuePosture, StringComparison.Ordinal)
                    && string.Equals(entitlementProjection.ReceiptStatus.ContinuePosture, "review_before_continue", StringComparison.Ordinal)
                    && string.Equals(entitlementProjection.ReceiptStatus.RecoveryRoute, "/account/access", StringComparison.Ordinal),
                "Standalone entitlement sync projection should keep its receipt-surface breakdown explicit and aligned with the filtered conflict receipt set.");
        }
        finally
        {
            if (Directory.Exists(tempRoot))
            {
                Directory.Delete(tempRoot, recursive: true);
            }
        }
    }

    private static void VerifyServerPlaneProvenanceReceiptsExposeRecoveryPosture()
    {
        MethodInfo projectMethod = typeof(CampaignWorkspaceServerPlaneService).GetMethod(
            "ProjectRestoreProvenanceRecoveryReceipts",
            BindingFlags.NonPublic | BindingFlags.Static)
            ?? throw new InvalidOperationException("Expected server-plane restore provenance recovery projection method.");

        WorkspaceRestoreProvenanceReceipt entitlementReceipt = new(
            ReceiptId: "receipt-entitlement",
            Kind: "active_entitlement",
            SubjectId: "grant-active",
            Surface: "entitlement_sync",
            Summary: "Active entitlement receipt.",
            Proof: "grant-active",
            ObservedAtUtc: DateTimeOffset.UtcNow);
        WorkspaceRestoreProvenanceReceipt artifactDriftReceipt = new(
            ReceiptId: "receipt-artifact-drift",
            Kind: "entitlement_artifact_drift",
            SubjectId: "artifact-old",
            Surface: "entitlement_sync",
            Summary: "Artifact drift receipt.",
            Proof: "artifact-old",
            ObservedAtUtc: DateTimeOffset.UtcNow);
        WorkspaceRestoreProvenanceReceipt staleInstallReceipt = new(
            ReceiptId: "receipt-stale-install",
            Kind: "claimed_installation_stale",
            SubjectId: "install-stale",
            Surface: "workspace_restore",
            Summary: "Stale install receipt.",
            Proof: "install-stale",
            ObservedAtUtc: DateTimeOffset.UtcNow);

        object? projected = projectMethod.Invoke(
            null,
            [new[] { entitlementReceipt, artifactDriftReceipt, staleInstallReceipt }]);
        IReadOnlyList<WorkspaceRestoreProvenanceRecoveryProjection> receipts =
            projected as IReadOnlyList<WorkspaceRestoreProvenanceRecoveryProjection>
            ?? throw new InvalidOperationException("Expected projected restore provenance recovery receipts.");

        WorkspaceRestoreProvenanceRecoveryProjection entitlementProjection =
            receipts.Single(item => string.Equals(item.ReceiptId, entitlementReceipt.ReceiptId, StringComparison.Ordinal));
        WorkspaceRestoreProvenanceRecoveryProjection artifactDriftProjection =
            receipts.Single(item => string.Equals(item.ReceiptId, artifactDriftReceipt.ReceiptId, StringComparison.Ordinal));
        WorkspaceRestoreProvenanceRecoveryProjection staleInstallProjection =
            receipts.Single(item => string.Equals(item.ReceiptId, staleInstallReceipt.ReceiptId, StringComparison.Ordinal));

        VerificationAssert.True(
            string.Equals(entitlementProjection.RecoveryRoute, "/account/access", StringComparison.Ordinal)
                && string.Equals(entitlementProjection.ContinuePosture, "safe_to_continue_with_receipt", StringComparison.Ordinal),
            "Entitlement provenance should expose account-access recovery and safe continuation posture.");
        VerificationAssert.True(
            entitlementProjection.RecoverySummary.Contains("/account/access", StringComparison.Ordinal)
                && entitlementProjection.RecoverySummary.Contains(entitlementReceipt.SubjectId, StringComparison.Ordinal),
            "Entitlement provenance recovery summaries should name the recovery route and receipt subject.");
        VerificationAssert.True(
            string.Equals(entitlementProjection.StalenessPosture, "current_receipt", StringComparison.Ordinal)
                && string.Equals(entitlementProjection.RecoverabilityPosture, "recoverable_with_receipt", StringComparison.Ordinal),
            "Current entitlement provenance should stay explicitly recoverable without stale-state inference.");
        VerificationAssert.True(
            string.Equals(artifactDriftProjection.RecoveryRoute, "/downloads", StringComparison.Ordinal)
                && string.Equals(artifactDriftProjection.ContinuePosture, "refresh_before_continue", StringComparison.Ordinal),
            "Artifact-drift provenance should route back to downloads and require refresh before continue.");
        VerificationAssert.True(
            artifactDriftProjection.RecoverySummary.Contains("/downloads", StringComparison.Ordinal)
                && artifactDriftProjection.RecoverySummary.Contains("before continuing", StringComparison.OrdinalIgnoreCase),
            "Artifact-drift provenance recovery summaries should make the download refresh posture explicit.");
        VerificationAssert.True(
            string.Equals(artifactDriftProjection.StalenessPosture, "artifact_drift", StringComparison.Ordinal)
                && string.Equals(artifactDriftProjection.RecoverabilityPosture, "recoverable_by_refresh", StringComparison.Ordinal),
            "Artifact-drift provenance should expose normalized stale-state and recoverability posture.");
        VerificationAssert.True(
            string.Equals(staleInstallProjection.RecoveryRoute, "/account/access", StringComparison.Ordinal)
                && string.Equals(staleInstallProjection.ContinuePosture, "refresh_before_continue", StringComparison.Ordinal),
            "Stale claimed-install provenance should route to account access and require refresh before continue.");
        VerificationAssert.True(
            string.Equals(staleInstallProjection.StalenessPosture, "stale_state", StringComparison.Ordinal)
                && string.Equals(staleInstallProjection.RecoverabilityPosture, "recoverable_by_refresh", StringComparison.Ordinal),
            "Stale claimed-install provenance should expose normalized stale-state recovery posture.");
    }

    private static void VerifyServerPlanePrioritizesRecoverableProvenanceReceipts()
    {
        MethodInfo receiptProjectMethod = typeof(CampaignWorkspaceServerPlaneService).GetMethod(
            "ProjectRestoreProvenanceReceipts",
            BindingFlags.NonPublic | BindingFlags.Static)
            ?? throw new InvalidOperationException("Expected server-plane restore provenance receipt projection method.");
        MethodInfo recoveryProjectMethod = typeof(CampaignWorkspaceServerPlaneService).GetMethod(
            "ProjectRestoreProvenanceRecoveryReceipts",
            BindingFlags.NonPublic | BindingFlags.Static)
            ?? throw new InvalidOperationException("Expected server-plane restore provenance recovery projection method.");

        DateTimeOffset now = DateTimeOffset.UtcNow;
        WorkspaceRestoreProvenanceReceipt routineInventory = new(
            ReceiptId: "receipt-routine-inventory",
            Kind: "restore_inventory_snapshot",
            SubjectId: "user-inventory",
            Surface: "workspace_restore",
            Summary: "Routine inventory receipt.",
            Proof: "inventory",
            ObservedAtUtc: now.AddMinutes(2));
        WorkspaceRestoreProvenanceReceipt routineEntitlement = new(
            ReceiptId: "receipt-routine-entitlement",
            Kind: "active_entitlement",
            SubjectId: "grant-safe",
            Surface: "entitlement_sync",
            Summary: "Routine entitlement receipt.",
            Proof: "grant-safe",
            ObservedAtUtc: now.AddMinutes(1));
        WorkspaceRestoreProvenanceReceipt artifactDrift = new(
            ReceiptId: "receipt-artifact-drift-priority",
            Kind: "entitlement_artifact_drift",
            SubjectId: "artifact-drift",
            Surface: "entitlement_sync",
            Summary: "Artifact drift receipt.",
            Proof: "artifact-drift",
            ObservedAtUtc: now);
        WorkspaceRestoreProvenanceReceipt staleClaim = new(
            ReceiptId: "receipt-stale-claim-priority",
            Kind: "claimed_installation_stale",
            SubjectId: "install-stale",
            Surface: "workspace_restore",
            Summary: "Stale claimed install receipt.",
            Proof: "install-stale",
            ObservedAtUtc: now.AddMinutes(-1));

        WorkspaceRestoreProvenanceReceipt[] sourceReceipts =
        [
            routineInventory,
            routineEntitlement,
            artifactDrift,
            staleClaim
        ];

        IReadOnlyList<WorkspaceRestoreProvenanceReceipt> receipts =
            receiptProjectMethod.Invoke(null, [sourceReceipts]) as IReadOnlyList<WorkspaceRestoreProvenanceReceipt>
            ?? throw new InvalidOperationException("Expected projected restore provenance receipts.");
        IReadOnlyList<WorkspaceRestoreProvenanceRecoveryProjection> recoveryReceipts =
            recoveryProjectMethod.Invoke(null, [sourceReceipts]) as IReadOnlyList<WorkspaceRestoreProvenanceRecoveryProjection>
            ?? throw new InvalidOperationException("Expected projected restore provenance recovery receipts.");

        VerificationAssert.True(
            string.Equals(receipts[0].ReceiptId, artifactDrift.ReceiptId, StringComparison.Ordinal)
                && string.Equals(receipts[1].ReceiptId, staleClaim.ReceiptId, StringComparison.Ordinal),
            "Recoverable stale and artifact-drift provenance receipts should sort before routine restore inventory so the account restore cap cannot hide them.");
        VerificationAssert.True(
            string.Equals(recoveryReceipts[0].ReceiptId, artifactDrift.ReceiptId, StringComparison.Ordinal)
                && string.Equals(recoveryReceipts[0].ContinuePosture, "refresh_before_continue", StringComparison.Ordinal)
                && string.Equals(recoveryReceipts[1].ReceiptId, staleClaim.ReceiptId, StringComparison.Ordinal),
            "Recoverable provenance recovery receipts should keep refresh-before-continue posture at the top of the restore recovery list.");
    }

    private static void VerifyServerPlaneNextSafeActionSurfacesRecoverableProvenance()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), "run-services-verification", "campaign-spine-restore-provenance-action", Guid.NewGuid().ToString("N"));
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
            WorkspaceLifecyclePolicyService lifecycle = new(configuration);
            CampaignSpineService campaignSpine = new(store, lifecycle, new CampaignArtifactRegistryBridge(store));
            HubUserDto user = accounts.EnsureUser("subject.restore.provenance.action", "Provenance", "provenance-action@example.invalid");
            CampaignWorkspaceProjection workspace = campaignSpine.GetStarterWorkspace(user)
                ?? throw new InvalidOperationException("Expected a starter workspace.");

            WorkspaceRestoreProvenanceReceipt routineInventory = new(
                ReceiptId: "receipt-routine-inventory-action",
                Kind: "workspace_inventory",
                SubjectId: "workspace-safe",
                Surface: "workspace_restore",
                Summary: "Routine restore inventory.",
                Proof: "workspace-safe",
                ObservedAtUtc: DateTimeOffset.UtcNow.AddMinutes(1));
            WorkspaceRestoreProvenanceReceipt staleEntitlement = new(
                ReceiptId: "receipt-stale-entitlement-action",
                Kind: "entitlement_replication_stale_claim",
                SubjectId: "grant-stale",
                Surface: "entitlement_sync",
                Summary: "Stale entitlement replication receipt.",
                Proof: "grant-stale",
                ObservedAtUtc: DateTimeOffset.UtcNow,
                Authority: "hub_entitlement_ledger",
                RecoveryHint: "Refresh account access before continuing with this grant.");
            WorkspaceRestoreProjection restore = new(
                RestoreId: "restore-provenance-action",
                UserId: user.UserId,
                RecentDossiers: [],
                RecentCampaigns: [],
                RecentRuleEnvironments: [],
                RecentArtifacts: [],
                Entitlements: [],
                ClaimedDevices: [],
                ConflictSummaries: [],
                LocalOnlyNotes: [],
                GeneratedAtUtc: DateTimeOffset.UtcNow,
                ProvenanceReceipts: [routineInventory, staleEntitlement],
                ConflictReceipts: []);

            MethodInfo nextSafeActionMethod = typeof(CampaignWorkspaceServerPlaneService).GetMethod(
                "BuildNextSafeActionCue",
                BindingFlags.NonPublic | BindingFlags.Static)
                ?? throw new InvalidOperationException("Expected server-plane next-safe-action method.");
            NextSafeActionCue nextSafeAction =
                nextSafeActionMethod.Invoke(null, [workspace, restore, null, Array.Empty<SupportCaseDigestViewModel>()]) as NextSafeActionCue
                ?? throw new InvalidOperationException("Expected restore next-safe-action cue.");

            VerificationAssert.True(
                nextSafeAction.ActionId.Contains("restore-provenance:", StringComparison.Ordinal)
                    && string.Equals(nextSafeAction.Label, "Refresh restore receipts", StringComparison.Ordinal)
                    && string.Equals(nextSafeAction.Summary, staleEntitlement.RecoveryHint, StringComparison.Ordinal)
                    && string.Equals(nextSafeAction.SourceKind, "restore", StringComparison.Ordinal),
                "Recoverable stale provenance should become the workspace next-safe action even when no conflict receipt has been emitted.");
        }
        finally
        {
            if (Directory.Exists(tempRoot))
            {
                Directory.Delete(tempRoot, recursive: true);
            }
        }
    }

    private static void VerifyEntitlementSyncProjectionStaysExplicitAndRecoverable()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), "run-services-verification", "campaign-spine-entitlement-sync", Guid.NewGuid().ToString("N"));
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
            WorkspaceLifecyclePolicyService lifecycle = new(configuration);
            CampaignSpineService campaignSpine = new(store, lifecycle, new CampaignArtifactRegistryBridge(store));
            CampaignWorkspaceServerPlaneService workspaceServerPlane = new(campaignSpine, null!, null!);

            HubUserDto user = accounts.EnsureUser("subject.restore.entitlement.sync", "Continuity", "continuity@example.invalid");
            DateTimeOffset now = DateTimeOffset.UtcNow;

            InstallLinkingSummaryDto installLinking = new(
                RecentReceipts:
                [
                    new DownloadReceiptDto(
                        ReceiptId: "receipt-sync-drift",
                        ArtifactId: "artifact-sync-stale",
                        ArtifactLabel: "Sync drift payload",
                        FileName: "sync-drift-linux.deb",
                        DownloadUrl: "/downloads/files/sync-drift-linux.deb",
                        Channel: "preview",
                        Version: "2026.02.01-preview.1",
                        Head: "avalonia",
                        Platform: "linux",
                        Arch: "x64",
                        Kind: "installer",
                        InstallAccessClass: InstallAccessClasses.AccountRecommended,
                        IssuedAtUtc: now.AddDays(-45),
                        UserId: user.UserId,
                        SubjectId: user.SubjectId,
                        ClaimTicketId: null,
                        ClaimCode: null,
                        ClaimTicketExpiresAtUtc: null)
                ],
                PendingClaimTickets: Array.Empty<InstallClaimTicketDto>(),
                ClaimedInstallations:
                [
                    new ClaimedInstallationDto(
                        InstallationId: "install-sync-stale",
                        ArtifactId: "artifact-sync-current",
                        Channel: "preview",
                        Version: "2026.04.01-preview.1",
                        InstallAccessClass: InstallAccessClasses.AccountRecommended,
                        Status: ClaimedInstallationStates.Active,
                        CreatedAtUtc: now.AddDays(-45),
                        UpdatedAtUtc: now.AddDays(-40),
                        UserId: user.UserId,
                        SubjectId: user.SubjectId,
                        PublicKey: "public-key-sync-stale",
                        ClaimTicketId: "ticket-sync-stale",
                        HeadId: "avalonia",
                        Platform: "linux",
                        Arch: "x64",
                        HostLabel: "Sync drift workstation",
                        GrantId: "grant-sync-a")
                ],
                ActiveGrants:
                [
                    new InstallationGrantDto(
                        GrantId: "grant-sync-a",
                        InstallationId: "install-sync-stale",
                        Status: InstallationGrantStates.Active,
                        AccessToken: "grant-sync-a-token",
                        IssuedAtUtc: now.AddDays(-12),
                        ExpiresAtUtc: now.AddDays(7),
                        UserId: user.UserId,
                        SubjectId: user.SubjectId),
                    new InstallationGrantDto(
                        GrantId: "grant-sync-b",
                        InstallationId: "install-sync-stale",
                        Status: InstallationGrantStates.Active,
                        AccessToken: "grant-sync-b-token",
                        IssuedAtUtc: now.AddDays(-11),
                        ExpiresAtUtc: now.AddDays(7),
                        UserId: user.UserId,
                        SubjectId: user.SubjectId)
                ]);

            EntitlementSyncReceiptProjection projection = workspaceServerPlane.GetEntitlementSyncReceiptProjection(user, installLinking);

            VerificationAssert.True(
                projection.ProvenanceReceipts.Count > 0
                    && projection.ProvenanceReceipts.All(item => string.Equals(item.Surface, "entitlement_sync", StringComparison.Ordinal)),
                "Entitlement sync projection should isolate entitlement-surface provenance receipts.");
            VerificationAssert.True(
                projection.ProvenanceRecoveryReceipts.Any(item =>
                    string.Equals(item.RecoveryRoute, "/account/access", StringComparison.Ordinal)
                    && (string.Equals(item.ContinuePosture, "safe_to_continue_with_receipt", StringComparison.Ordinal)
                        || string.Equals(item.ContinuePosture, "refresh_before_continue", StringComparison.Ordinal))),
                "Entitlement sync projection should keep recoverable account-access provenance cues explicit.");
            VerificationAssert.True(
                projection.ConflictReceipts.Count > 0
                    && projection.ConflictReceipts.All(item => string.Equals(item.Surface, "entitlement_sync", StringComparison.Ordinal)),
                "Entitlement sync projection should isolate entitlement-sync conflict receipts.");
            VerificationAssert.True(
                projection.ConflictReceipts.Any(item =>
                    string.Equals(item.Kind, "entitlement_replication_duplicate_grant", StringComparison.OrdinalIgnoreCase)
                    && item.BlocksContinue
                    && string.Equals(item.RecoveryRoute, "/account/access", StringComparison.Ordinal)),
                "Entitlement sync projection should keep duplicate-grant conflicts blocking and recoverable through account access.");
            VerificationAssert.True(
                projection.ReceiptStatus.EntitlementSyncConflictCount == projection.ConflictReceipts.Count
                    && projection.ReceiptStatus.WorkspaceRestoreConflictCount == 0
                    && projection.ReceiptStatus.EntitlementSyncProvenanceCount == projection.ProvenanceReceipts.Count
                    && projection.ReceiptStatus.WorkspaceRestoreProvenanceCount == 0,
                "Entitlement sync status should summarize only the entitlement-sync slice instead of mixing workspace restore counts back in.");
            VerificationAssert.True(
                !string.IsNullOrWhiteSpace(projection.ReceiptStatus.LeadRecoveryHint)
                    && string.Equals(projection.ReceiptStatus.LeadSurface, "entitlement_sync", StringComparison.Ordinal)
                    && !string.IsNullOrWhiteSpace(projection.ReceiptStatus.RecoverySummary),
                "Entitlement sync status should keep one explicit recoverable lead receipt for standalone access surfaces.");
        }
        finally
        {
            if (Directory.Exists(tempRoot))
            {
                Directory.Delete(tempRoot, recursive: true);
            }
        }
    }

    private static void VerifyServerPlaneRestoreReceiptStatusSummarizesBlockingRecovery()
    {
        MethodInfo projectMethod = typeof(CampaignWorkspaceServerPlaneService).GetMethod(
            "BuildRestoreReceiptStatusProjection",
            BindingFlags.NonPublic | BindingFlags.Static)
            ?? throw new InvalidOperationException("Expected restore receipt status projection method.");

        IReadOnlyList<WorkspaceRestoreProvenanceReceipt> provenanceReceipts =
        [
            new(
                ReceiptId: "workspace-current",
                Kind: "restore_inventory_snapshot",
                SubjectId: "workspace-safe",
                Surface: "workspace_restore",
                Summary: "Workspace inventory is current.",
                Proof: "inventory",
                ObservedAtUtc: DateTimeOffset.UtcNow.AddMinutes(1)),
            new(
                ReceiptId: "entitlement-stale",
                Kind: "entitlement_replication_stale_claim",
                SubjectId: "grant-stale",
                Surface: "entitlement_sync",
                Summary: "Grant points at stale claim state.",
                Proof: "grant-stale",
                ObservedAtUtc: DateTimeOffset.UtcNow)
        ];
        IReadOnlyList<WorkspaceRestoreProvenanceRecoveryProjection> provenanceRecoveryReceipts =
        [
            new(
                ReceiptId: "workspace-current",
                Kind: "restore_inventory_snapshot",
                SubjectId: "workspace-safe",
                Surface: "workspace_restore",
                Summary: "Workspace inventory is current.",
                Proof: "inventory",
                ObservedAtUtc: DateTimeOffset.UtcNow.AddMinutes(1),
                Authority: "hub_campaign_spine_projection",
                StalenessPosture: "current_receipt",
                RecoverabilityPosture: "recoverable_with_receipt",
                RecoveryHint: "Review the restore rail if inventory drifts.",
                RecoveryRoute: "/account/work",
                RecoverySummary: "Inventory is current on the restore rail.",
                ContinuePosture: "safe_to_continue_with_receipt"),
            new(
                ReceiptId: "entitlement-stale",
                Kind: "entitlement_replication_stale_claim",
                SubjectId: "grant-stale",
                Surface: "entitlement_sync",
                Summary: "Grant points at stale claim state.",
                Proof: "grant-stale",
                ObservedAtUtc: DateTimeOffset.UtcNow,
                Authority: "hub_entitlement_ledger",
                StalenessPosture: "stale_state",
                RecoverabilityPosture: "recoverable_by_refresh",
                RecoveryHint: "Refresh account access before continuing.",
                RecoveryRoute: "/account/access",
                RecoverySummary: "Refresh grant-stale through /account/access before continuing from this restored workspace.",
                ContinuePosture: "refresh_before_continue")
        ];
        IReadOnlyList<WorkspaceRestoreConflictReceiptProjection> conflictReceipts =
        [
            new(
                ReceiptId: "blocking-artifact-drift",
                Severity: "blocking",
                Kind: "entitlement_artifact_drift",
                Surface: "entitlement_sync",
                Authority: "hub_registry_release_receipts",
                SubjectId: "install-artifact",
                Summary: "Artifact drift blocks restore continuation.",
                Resolution: "Refresh the signed-in download or install rail before continuing on this workspace.",
                ConflictPosture: "blocking_conflict",
                RecoverabilityPosture: "recoverable_by_download_refresh_before_continue",
                RecoveryRoute: "/downloads",
                RecoveryHint: "Refresh the signed-in download or install rail for install-artifact so artifact truth matches entitlement replay before continuing.",
                RecoverySummary: "Resolve install-artifact through /downloads before continuing from this restored workspace.",
                ContinuePosture: "blocked_until_receipt_resolved",
                ObservedAtUtc: DateTimeOffset.UtcNow.AddMinutes(2),
                BlocksContinue: true)
        ];

        WorkspaceRestoreReceiptStatusProjection status =
            projectMethod.Invoke(
                null,
                [provenanceReceipts, provenanceRecoveryReceipts, conflictReceipts, Enum.Parse(projectMethod.GetParameters()[3].ParameterType, "Restore")]) as WorkspaceRestoreReceiptStatusProjection
            ?? throw new InvalidOperationException("Expected restore receipt status projection.");

        VerificationAssert.True(
            string.Equals(status.StalenessPosture, "stale_or_drift_receipts_present", StringComparison.Ordinal)
                && string.Equals(status.ConflictPosture, "blocking_conflict_present", StringComparison.Ordinal)
                && string.Equals(status.ContinuePosture, "blocked_until_receipt_resolved", StringComparison.Ordinal),
            "Restore receipt status should summarize stale-state and blocking-conflict posture instead of leaving users to infer it from raw receipt rows.");
        VerificationAssert.True(
            string.Equals(status.LeadReceiptId, "blocking-artifact-drift", StringComparison.Ordinal)
                && string.Equals(status.LeadSurface, "entitlement_sync", StringComparison.Ordinal)
                && string.Equals(status.LeadAuthority, "hub_registry_release_receipts", StringComparison.Ordinal)
                && string.Equals(status.LeadKind, "entitlement_artifact_drift", StringComparison.Ordinal)
                && string.Equals(status.LeadSubjectId, "install-artifact", StringComparison.Ordinal),
            "Restore receipt status should expose the lead blocking receipt identity, surface, authority, kind, and subject.");
        VerificationAssert.True(
            string.Equals(status.RecoveryRoute, "/downloads", StringComparison.Ordinal)
                && status.RecoverySummary.Contains("/downloads", StringComparison.Ordinal)
                && string.Equals(status.RecoverabilityPosture, "recoverable_by_download_refresh_before_continue", StringComparison.Ordinal),
            "Restore receipt status should surface the lead recovery route and recoverability posture from the highest-priority blocking receipt.");
        VerificationAssert.True(
            status.ProvenanceSummary.Contains("Restore provenance keeps 2 receipt(s) explicit", StringComparison.Ordinal)
                && status.ProvenanceSummary.Contains("1 workspace restore, 1 entitlement sync", StringComparison.Ordinal)
                && status.ConflictSummary.Contains("Restore conflicts keep 1 receipt(s) explicit", StringComparison.Ordinal)
                && status.ConflictSummary.Contains("1 entitlement sync, 1 blocking", StringComparison.Ordinal),
            "Restore receipt status should expose dedicated provenance and conflict summaries so callers do not have to reverse-engineer the mixed status summary.");
        VerificationAssert.True(
            status.LeadRecoveryHint.Contains("signed-in download or install rail", StringComparison.Ordinal)
                && status.LeadRecoveryHint.Contains("install-artifact", StringComparison.Ordinal),
            "Restore receipt status should expose the lead recovery hint instead of forcing callers to infer it from the raw receipt list.");
        VerificationAssert.True(
            string.Equals(status.RecoveryActionLabel, "Open downloads", StringComparison.Ordinal),
            "Restore receipt status should expose a direct recovery action label for the lead recovery route.");
        VerificationAssert.True(
            status.LeadObservedAtUtc == conflictReceipts[0].ObservedAtUtc
                && status.LatestReceiptObservedAtUtc == conflictReceipts[0].ObservedAtUtc,
            "Restore receipt status should expose the lead and latest receipt observation times so stale continuity posture is reviewable without scanning every receipt row.");
        VerificationAssert.True(
            status.CurrentProvenanceReceiptCount == 1
                && status.StaleOrDriftProvenanceReceiptCount == 1,
            "Restore receipt status should keep current-vs-stale provenance counts explicit instead of hiding stale restore posture inside a summary string.");
        VerificationAssert.True(
            status.SafeToContinueWithReceiptCount == 1
                && status.RefreshBeforeContinueCount == 1
                && status.ReviewBeforeContinueConflictCount == 0
                && status.BlockingConflictCount == 1
                && status.WorkspaceRestoreProvenanceCount == 1
                && status.EntitlementSyncProvenanceCount == 1
                && status.EntitlementSyncConflictCount == 1,
            "Restore receipt status should keep explicit workspace, entitlement, safe, refresh, review, and blocking counts.");
    }

    private static void VerifyServerPlaneRestoreReceiptStatusFallsBackToRecoverableProvenanceLead()
    {
        MethodInfo projectMethod = typeof(CampaignWorkspaceServerPlaneService).GetMethod(
            "BuildRestoreReceiptStatusProjection",
            BindingFlags.NonPublic | BindingFlags.Static)
            ?? throw new InvalidOperationException("Expected restore receipt status projection method.");

        IReadOnlyList<WorkspaceRestoreProvenanceReceipt> provenanceReceipts =
        [
            new(
                ReceiptId: "stale-claimed-install",
                Kind: "claimed_installation_stale",
                SubjectId: "install-stale",
                Surface: "workspace_restore",
                Summary: "Claimed installation is stale.",
                Proof: "install-stale",
                ObservedAtUtc: DateTimeOffset.UtcNow)
        ];
        IReadOnlyList<WorkspaceRestoreProvenanceRecoveryProjection> provenanceRecoveryReceipts =
        [
            new(
                ReceiptId: "stale-claimed-install",
                Kind: "claimed_installation_stale",
                SubjectId: "install-stale",
                Surface: "workspace_restore",
                Summary: "Claimed installation is stale.",
                Proof: "install-stale",
                ObservedAtUtc: DateTimeOffset.UtcNow,
                Authority: "hub_registry_install_linking",
                StalenessPosture: "stale_state",
                RecoverabilityPosture: "recoverable_by_refresh",
                RecoveryHint: "Relink claimed install install-stale from account access so workspace restore can recover current device state.",
                RecoveryRoute: "/account/access",
                RecoverySummary: "Refresh install-stale through /account/access before continuing from this restored workspace.",
                ContinuePosture: "refresh_before_continue")
        ];

        WorkspaceRestoreReceiptStatusProjection status =
            projectMethod.Invoke(
                null,
                [provenanceReceipts, provenanceRecoveryReceipts, Array.Empty<WorkspaceRestoreConflictReceiptProjection>(), Enum.Parse(projectMethod.GetParameters()[3].ParameterType, "Restore")]) as WorkspaceRestoreReceiptStatusProjection
            ?? throw new InvalidOperationException("Expected restore receipt status projection.");

        VerificationAssert.True(
            string.Equals(status.ContinuePosture, "refresh_before_continue", StringComparison.Ordinal)
                && string.Equals(status.LeadReceiptId, "stale-claimed-install", StringComparison.Ordinal)
                && string.Equals(status.LeadSurface, "workspace_restore", StringComparison.Ordinal)
                && string.Equals(status.LeadAuthority, "hub_registry_install_linking", StringComparison.Ordinal)
                && string.Equals(status.LeadKind, "claimed_installation_stale", StringComparison.Ordinal)
                && string.Equals(status.LeadSubjectId, "install-stale", StringComparison.Ordinal),
            "Restore receipt status should fall back to the lead recoverable provenance receipt when no blocking conflict is present.");
        VerificationAssert.True(
            string.Equals(status.RecoveryRoute, "/account/access", StringComparison.Ordinal)
                && status.LeadRecoveryHint.Contains("Relink claimed install", StringComparison.Ordinal)
                && status.RecoverySummary.Contains("/account/access", StringComparison.Ordinal)
                && string.Equals(status.RecoveryActionLabel, "Open account access", StringComparison.Ordinal)
                && status.LeadObservedAtUtc == provenanceRecoveryReceipts[0].ObservedAtUtc
                && status.LatestReceiptObservedAtUtc == provenanceRecoveryReceipts[0].ObservedAtUtc
                && status.CurrentProvenanceReceiptCount == 0
                && status.StaleOrDriftProvenanceReceiptCount == 1
                && status.SafeToContinueWithReceiptCount == 0
                && status.RefreshBeforeContinueCount == 1
                && status.ReviewBeforeContinueConflictCount == 0
                && status.BlockingConflictCount == 0,
            "Restore receipt status should keep recoverable stale workspace restore posture explicit even without a conflict receipt.");
    }

    private static void VerifyRestoreReceiptStatusEmitsTypedRecoveryActions()
    {
        MethodInfo projectMethod = typeof(CampaignWorkspaceServerPlaneService).GetMethod(
            "BuildRestoreReceiptStatusProjection",
            BindingFlags.NonPublic | BindingFlags.Static)
            ?? throw new InvalidOperationException("Expected restore receipt status projection method.");

        DateTimeOffset now = DateTimeOffset.UtcNow;
        IReadOnlyList<WorkspaceRestoreProvenanceReceipt> provenanceReceipts =
        [
            new(
                ReceiptId: "workspace-current-action",
                Kind: "restore_inventory_snapshot",
                SubjectId: "workspace-safe",
                Surface: "workspace_restore",
                Summary: "Workspace inventory is current.",
                Proof: "inventory",
                ObservedAtUtc: now.AddMinutes(1)),
            new(
                ReceiptId: "entitlement-stale-action",
                Kind: "entitlement_replication_stale_claim",
                SubjectId: "grant-stale",
                Surface: "entitlement_sync",
                Summary: "Grant points at stale claim state.",
                Proof: "grant-stale",
                ObservedAtUtc: now)
        ];
        IReadOnlyList<WorkspaceRestoreProvenanceRecoveryProjection> provenanceRecoveryReceipts =
        [
            new(
                ReceiptId: "workspace-current-action",
                Kind: "restore_inventory_snapshot",
                SubjectId: "workspace-safe",
                Surface: "workspace_restore",
                Summary: "Workspace inventory is current.",
                Proof: "inventory",
                ObservedAtUtc: now.AddMinutes(1),
                Authority: "hub_campaign_spine_projection",
                StalenessPosture: "current_receipt",
                RecoverabilityPosture: "recoverable_with_receipt",
                RecoveryHint: "Review the restore rail if inventory drifts.",
                RecoveryRoute: "/account/work",
                RecoverySummary: "Inventory is current on the restore rail.",
                ContinuePosture: "safe_to_continue_with_receipt"),
            new(
                ReceiptId: "entitlement-stale-action",
                Kind: "entitlement_replication_stale_claim",
                SubjectId: "grant-stale",
                Surface: "entitlement_sync",
                Summary: "Grant points at stale claim state.",
                Proof: "grant-stale",
                ObservedAtUtc: now,
                Authority: "hub_entitlement_ledger",
                StalenessPosture: "stale_state",
                RecoverabilityPosture: "recoverable_by_refresh",
                RecoveryHint: "Refresh account access before continuing.",
                RecoveryRoute: "/account/access",
                RecoverySummary: "Refresh grant-stale through /account/access before continuing from this restored workspace.",
                ContinuePosture: "refresh_before_continue")
        ];
        IReadOnlyList<WorkspaceRestoreConflictReceiptProjection> conflictReceipts =
        [
            new(
                ReceiptId: "blocking-entitlement-action",
                Severity: "blocking",
                Kind: "entitlement_replication_duplicate_grant",
                Surface: "entitlement_sync",
                Authority: "hub_entitlement_ledger",
                SubjectId: "install-duplicate",
                Summary: "Duplicate entitlement receipts block restore continuation.",
                Resolution: "Open account access and rotate duplicate grants.",
                ConflictPosture: "blocking_conflict",
                RecoverabilityPosture: "recoverable_by_account_access_before_continue",
                RecoveryRoute: "/account/access",
                RecoveryHint: "Open account access and refresh entitlement replication.",
                RecoverySummary: "Resolve install-duplicate through /account/access before continuing from this restored workspace.",
                ContinuePosture: "blocked_until_receipt_resolved",
                ObservedAtUtc: now.AddMinutes(2),
                BlocksContinue: true)
        ];

        Type scopeType = projectMethod.GetParameters()[3].ParameterType;
        WorkspaceRestoreReceiptStatusProjection status =
            projectMethod.Invoke(
                null,
                [provenanceReceipts, provenanceRecoveryReceipts, conflictReceipts, Enum.Parse(scopeType, "Restore")]) as WorkspaceRestoreReceiptStatusProjection
            ?? throw new InvalidOperationException("Expected restore receipt status projection.");
        WorkspaceRestoreReceiptStatusProjection emptyEntitlementStatus =
            projectMethod.Invoke(
                null,
                [
                    Array.Empty<WorkspaceRestoreProvenanceReceipt>(),
                    Array.Empty<WorkspaceRestoreProvenanceRecoveryProjection>(),
                    Array.Empty<WorkspaceRestoreConflictReceiptProjection>(),
                    Enum.Parse(scopeType, "EntitlementSync")
                ]) as WorkspaceRestoreReceiptStatusProjection
            ?? throw new InvalidOperationException("Expected fallback entitlement sync status projection.");

        VerificationAssert.True(
            status.RecoveryActions.Count >= 3
                && status.RecoveryActions[0].BlocksContinue
                && string.Equals(status.RecoveryActions[0].ReceiptId, "blocking-entitlement-action", StringComparison.Ordinal)
                && string.Equals(status.RecoveryActions[0].Authority, "hub_entitlement_ledger", StringComparison.Ordinal)
                && string.Equals(status.RecoveryActions[0].Route, "/account/access", StringComparison.Ordinal)
                && string.Equals(status.RecoveryActions[0].ContinuePosture, "blocked_until_receipt_resolved", StringComparison.Ordinal)
                && status.RecoveryActions.Any(item =>
                    string.Equals(item.ReceiptId, "entitlement-stale-action", StringComparison.Ordinal)
                    && string.Equals(item.Authority, "hub_entitlement_ledger", StringComparison.Ordinal)
                    && string.Equals(item.ContinuePosture, "refresh_before_continue", StringComparison.Ordinal)
                    && string.Equals(item.Label, "Open account access", StringComparison.Ordinal))
                && status.RecoveryActions.Any(item =>
                    string.Equals(item.ReceiptId, "workspace-current-action", StringComparison.Ordinal)
                    && string.Equals(item.Authority, "hub_campaign_spine_projection", StringComparison.Ordinal)
                    && string.Equals(item.Route, "/account/work", StringComparison.Ordinal)
                    && string.Equals(item.ContinuePosture, "safe_to_continue_with_receipt", StringComparison.Ordinal)),
            "Restore receipt status should emit typed recovery actions with authority for blocking conflicts, stale provenance, and current workspace receipts so clients do not parse summaries.");
        VerificationAssert.True(
            emptyEntitlementStatus.RecoveryActions.Count == 1
                && string.Equals(emptyEntitlementStatus.RecoveryActions[0].ActionId, "entitlement-sync:review-required", StringComparison.Ordinal)
                && string.Equals(emptyEntitlementStatus.RecoveryActions[0].Authority, "hub_entitlement_ledger", StringComparison.Ordinal)
                && string.Equals(emptyEntitlementStatus.RecoveryActions[0].Surface, "entitlement_sync", StringComparison.Ordinal)
                && string.Equals(emptyEntitlementStatus.RecoveryActions[0].Route, "/account/access", StringComparison.Ordinal)
                && string.Equals(emptyEntitlementStatus.RecoveryActions[0].ContinuePosture, "review_before_continue", StringComparison.Ordinal),
            "Empty entitlement sync status should still emit one typed account-access review action instead of leaving recovery implicit.");
    }

    private static void VerifyEntitlementSyncReceiptStatusUsesStandaloneScopeDefaults()
    {
        MethodInfo projectMethod = typeof(CampaignWorkspaceServerPlaneService).GetMethod(
            "BuildRestoreReceiptStatusProjection",
            BindingFlags.NonPublic | BindingFlags.Static)
            ?? throw new InvalidOperationException("Expected restore receipt status projection method.");

        Type scopeType = projectMethod.GetParameters()[3].ParameterType;
        WorkspaceRestoreReceiptStatusProjection status =
            projectMethod.Invoke(
                null,
                [
                    Array.Empty<WorkspaceRestoreProvenanceReceipt>(),
                    Array.Empty<WorkspaceRestoreProvenanceRecoveryProjection>(),
                    Array.Empty<WorkspaceRestoreConflictReceiptProjection>(),
                    Enum.Parse(scopeType, "EntitlementSync")
                ]) as WorkspaceRestoreReceiptStatusProjection
            ?? throw new InvalidOperationException("Expected restore receipt status projection.");

        VerificationAssert.True(
            string.Equals(status.LeadReceiptId, "entitlement_sync_review_required", StringComparison.Ordinal)
                && string.Equals(status.LeadSurface, "entitlement_sync", StringComparison.Ordinal)
                && string.Equals(status.LeadAuthority, "hub_entitlement_ledger", StringComparison.Ordinal)
                && string.Equals(status.LeadKind, "entitlement_sync_review", StringComparison.Ordinal)
                && string.Equals(status.LeadSubjectId, "entitlement-sync", StringComparison.Ordinal),
            "Standalone entitlement sync status should default to entitlement-scoped lead receipt identity instead of workspace-restore fallback values.");
        VerificationAssert.True(
            string.Equals(status.RecoveryRoute, "/account/access", StringComparison.Ordinal)
                && string.Equals(status.RecoveryActionLabel, "Open account access", StringComparison.Ordinal)
                && string.Equals(status.LeadRecoveryHint, "Open account access and review entitlement sync receipts before trusting this device.", StringComparison.Ordinal)
                && string.Equals(status.RecoverySummary, "Review entitlement sync receipts through /account/access before continuing from this device.", StringComparison.Ordinal),
            "Standalone entitlement sync status should default to the account-access recovery lane when no receipts have been minted yet.");
        VerificationAssert.True(
            status.Summary.Contains("entitlement-sync provenance receipt(s)", StringComparison.Ordinal)
                && status.Summary.Contains("entitlement-sync conflict receipt(s)", StringComparison.Ordinal)
                && status.Summary.Contains("entitlement replication posture", StringComparison.Ordinal)
                && status.ProvenanceSummary.Contains("Entitlement sync provenance keeps 0 receipt(s) explicit", StringComparison.Ordinal)
                && status.ConflictSummary.Contains("Entitlement sync conflicts keep 0 receipt(s) explicit", StringComparison.Ordinal),
            "Standalone entitlement sync status summary should name entitlement-sync receipts and entitlement replication posture instead of generic restore wording.");
    }

    private static void VerifyServerPlaneProvenanceReceiptsRecoverBlankIdentityFields()
    {
        MethodInfo projectMethod = typeof(CampaignWorkspaceServerPlaneService).GetMethod(
            "ProjectRestoreProvenanceRecoveryReceipts",
            BindingFlags.NonPublic | BindingFlags.Static)
            ?? throw new InvalidOperationException("Expected server-plane restore provenance recovery projection method.");

        WorkspaceRestoreProvenanceReceipt blankIdentityReceipt = new(
            ReceiptId: " ",
            Kind: null!,
            SubjectId: "",
            Surface: "entitlement_sync",
            Summary: " ",
            Proof: null,
            ObservedAtUtc: DateTimeOffset.UtcNow);

        object? projected = projectMethod.Invoke(
            null,
            [new[] { blankIdentityReceipt }]);
        IReadOnlyList<WorkspaceRestoreProvenanceRecoveryProjection> receipts =
            projected as IReadOnlyList<WorkspaceRestoreProvenanceRecoveryProjection>
            ?? throw new InvalidOperationException("Expected projected restore provenance recovery receipts.");
        WorkspaceRestoreProvenanceRecoveryProjection receipt = receipts.Single();

        VerificationAssert.True(
            string.Equals(receipt.ReceiptId, "entitlement_sync:entitlement_restore_provenance:unknown_restore_subject:provenance", StringComparison.Ordinal),
            "Blank restore provenance receipt ids should recover a deterministic surface, kind, and subject receipt id.");
        VerificationAssert.True(
            string.Equals(receipt.Kind, "entitlement_restore_provenance", StringComparison.Ordinal),
            "Blank entitlement restore provenance kinds should recover an entitlement-sync provenance kind.");
        VerificationAssert.True(
            string.Equals(receipt.SubjectId, "unknown restore subject", StringComparison.Ordinal),
            "Blank restore provenance subjects should recover an explicit unknown-subject posture.");
        VerificationAssert.True(
            receipt.Summary.Contains("unknown restore subject", StringComparison.Ordinal),
            "Recovered blank-subject restore provenance summaries should name the unknown restore subject.");
        VerificationAssert.True(
            string.Equals(
                receipt.Proof,
                "hub_entitlement_ledger:entitlement_sync:entitlement_restore_provenance:unknown_restore_subject",
                StringComparison.Ordinal),
            "Blank restore provenance proof should recover authority, surface, kind, and subject posture.");
    }

    private static void VerifyServerPlaneActionsRecoverBlankBlockingConflictResolutions()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), "run-services-verification", "campaign-spine-restore-action-recovery", Guid.NewGuid().ToString("N"));
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
            WorkspaceLifecyclePolicyService lifecycle = new(configuration);
            CampaignSpineService campaignSpine = new(store, lifecycle, new CampaignArtifactRegistryBridge(store));
            HubUserDto user = accounts.EnsureUser("subject.restore.action", "Patch", "patch@example.invalid");
            CampaignWorkspaceProjection workspace = campaignSpine.GetStarterWorkspace(user)
                ?? throw new InvalidOperationException("Expected a starter workspace.");

            WorkspaceRestoreConflictReceipt blockingConflict = new(
                ReceiptId: null!,
                Severity: "attention",
                Kind: "entitlement_orphan",
                SubjectId: "grant-action",
                Summary: "",
                Resolution: " ",
                ObservedAtUtc: DateTimeOffset.UtcNow,
                Surface: "entitlement_sync",
                BlocksContinue: true);
            WorkspaceRestoreProjection restore = new(
                RestoreId: "restore-action",
                UserId: user.UserId,
                RecentDossiers: [],
                RecentCampaigns: [],
                RecentRuleEnvironments: [],
                RecentArtifacts: [],
                Entitlements: [],
                ClaimedDevices: [],
                ConflictSummaries: [],
                LocalOnlyNotes: [],
                GeneratedAtUtc: DateTimeOffset.UtcNow,
                ProvenanceReceipts: [],
                ConflictReceipts: [blockingConflict]);

            MethodInfo continuityMethod = typeof(CampaignWorkspaceServerPlaneService).GetMethod(
                "BuildContinuityConflicts",
                BindingFlags.NonPublic | BindingFlags.Static)
                ?? throw new InvalidOperationException("Expected server-plane continuity conflict method.");
            IReadOnlyList<ContinuityConflictCue> continuityCues =
                continuityMethod.Invoke(null, [workspace, restore]) as IReadOnlyList<ContinuityConflictCue>
                ?? throw new InvalidOperationException("Expected projected continuity conflict cues.");

            MethodInfo nextSafeActionMethod = typeof(CampaignWorkspaceServerPlaneService).GetMethod(
                "BuildNextSafeActionCue",
                BindingFlags.NonPublic | BindingFlags.Static)
                ?? throw new InvalidOperationException("Expected server-plane next-safe-action method.");
            NextSafeActionCue nextSafeAction =
                nextSafeActionMethod.Invoke(null, [workspace, restore, null, Array.Empty<SupportCaseDigestViewModel>()]) as NextSafeActionCue
                ?? throw new InvalidOperationException("Expected restore next-safe-action cue.");

            VerificationAssert.True(
                continuityCues.Any(item =>
                    item.CueId.Contains("restore-conflict:", StringComparison.Ordinal)
                    && item.CueId.Length > "restore-conflict:".Length
                    && string.Equals(item.Severity, "blocking", StringComparison.Ordinal)
                    && string.Equals(item.ResolutionAction, "Open account access and resolve this restore receipt before continuing on this workspace.", StringComparison.Ordinal)),
                "Continuity conflict cues should recover deterministic cue ids, keep explicit blocking severity, and recover the standard restore resolution when the source receipt identity or resolution is blank.");
            VerificationAssert.True(
                nextSafeAction.ActionId.Contains("restore:", StringComparison.Ordinal)
                    && nextSafeAction.ActionId.Split(':').Length >= 3,
                "Restore-driven next-safe-action cues should recover deterministic action ids when the source receipt identity is blank.");
            VerificationAssert.True(
                string.Equals(nextSafeAction.Summary, "Open account access and resolve this restore receipt before continuing on this workspace.", StringComparison.Ordinal),
                "Restore-driven next-safe-action cues should recover the same standard blocking restore resolution when the source receipt resolution is blank.");
        }
        finally
        {
            if (Directory.Exists(tempRoot))
            {
                Directory.Delete(tempRoot, recursive: true);
            }
        }
    }

    private static void VerifyServerPlanePrioritizesReceiptBackedConflictsOverSummaryOverflow()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), "run-services-verification", "campaign-spine-restore-conflict-priority", Guid.NewGuid().ToString("N"));
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
            WorkspaceLifecyclePolicyService lifecycle = new(configuration);
            CampaignSpineService campaignSpine = new(store, lifecycle, new CampaignArtifactRegistryBridge(store));
            HubUserDto user = accounts.EnsureUser("subject.restore.priority", "Priority", "priority@example.invalid");
            CampaignWorkspaceProjection workspace = campaignSpine.GetStarterWorkspace(user)
                ?? throw new InvalidOperationException("Expected a starter workspace.");

            WorkspaceRestoreConflictReceipt blockingReceipt = new(
                ReceiptId: "entitlement-priority",
                Severity: "attention",
                Kind: "entitlement_artifact_drift",
                SubjectId: "artifact-priority",
                Summary: "The entitlement artifact receipt does not match this claimed install.",
                Resolution: "Refresh the signed desktop payload before continuing.",
                ObservedAtUtc: DateTimeOffset.UtcNow,
                Surface: "entitlement_sync",
                BlocksContinue: true);
            WorkspaceRestoreProjection restore = new(
                RestoreId: "restore-priority",
                UserId: user.UserId,
                RecentDossiers: [],
                RecentCampaigns: [],
                RecentRuleEnvironments: [],
                RecentArtifacts: [],
                Entitlements: [],
                ClaimedDevices: [],
                ConflictSummaries:
                [
                    "Summary overflow 1",
                    "Summary overflow 2",
                    "Summary overflow 3",
                    "Summary overflow 4",
                    "Summary overflow 5",
                    "Summary overflow 6",
                    "Summary overflow 7",
                ],
                LocalOnlyNotes: [],
                GeneratedAtUtc: DateTimeOffset.UtcNow,
                ProvenanceReceipts: [],
                ConflictReceipts: [blockingReceipt]);

            MethodInfo continuityMethod = typeof(CampaignWorkspaceServerPlaneService).GetMethod(
                "BuildContinuityConflicts",
                BindingFlags.NonPublic | BindingFlags.Static)
                ?? throw new InvalidOperationException("Expected server-plane continuity conflict method.");
            IReadOnlyList<ContinuityConflictCue> continuityCues =
                continuityMethod.Invoke(null, [workspace, restore]) as IReadOnlyList<ContinuityConflictCue>
                ?? throw new InvalidOperationException("Expected projected continuity conflict cues.");

            VerificationAssert.True(
                continuityCues.Count == 6
                    && continuityCues[0].CueId.Contains("restore-conflict:", StringComparison.Ordinal)
                    && string.Equals(continuityCues[0].Severity, "blocking", StringComparison.Ordinal)
                    && string.Equals(continuityCues[0].ResolutionAction, blockingReceipt.Resolution, StringComparison.Ordinal),
                "Receipt-backed blocking restore conflicts should be prioritized before generic conflict summaries so the six-cue continuity cap cannot hide recoverable entitlement receipts.");
        }
        finally
        {
            if (Directory.Exists(tempRoot))
            {
                Directory.Delete(tempRoot, recursive: true);
            }
        }
    }

    private static void VerifyServerPlaneConflictReceiptsRecoverBlankSummaries()
    {
        MethodInfo projectMethod = typeof(CampaignWorkspaceServerPlaneService).GetMethod(
            "ProjectRestoreConflictReceipts",
            BindingFlags.NonPublic | BindingFlags.Static)
            ?? throw new InvalidOperationException("Expected server-plane restore conflict projection method.");

        WorkspaceRestoreConflictReceipt entitlementConflict = new(
            ReceiptId: "receipt-blank-entitlement",
            Severity: "attention",
            Kind: "entitlement_orphan",
            SubjectId: "grant-orphan",
            Summary: " ",
            Resolution: null,
            ObservedAtUtc: DateTimeOffset.UtcNow,
            Surface: "entitlement_sync",
            BlocksContinue: true);
        WorkspaceRestoreConflictReceipt workspaceConflict = new(
            ReceiptId: "receipt-blank-workspace",
            Severity: "warning",
            Kind: "claimed_installation_stale",
            SubjectId: "install-stale",
            Summary: "",
            Resolution: "Refresh this install before reopening the workspace.",
            ObservedAtUtc: DateTimeOffset.UtcNow,
            Surface: "workspace_restore",
            BlocksContinue: false);
        WorkspaceRestoreConflictReceipt artifactDriftConflict = new(
            ReceiptId: "receipt-artifact-drift",
            Severity: "blocking",
            Kind: "entitlement_artifact_drift",
            SubjectId: "artifact-stale",
            Summary: "Artifact receipt no longer matches the claimed install.",
            Resolution: "Refresh the signed desktop payload before continuing.",
            ObservedAtUtc: DateTimeOffset.UtcNow,
            Surface: "entitlement_sync",
            BlocksContinue: true);

        object? projected = projectMethod.Invoke(
            null,
            [new[] { entitlementConflict, workspaceConflict, artifactDriftConflict }]);
        IReadOnlyList<WorkspaceRestoreConflictReceiptProjection> receipts =
            projected as IReadOnlyList<WorkspaceRestoreConflictReceiptProjection>
            ?? throw new InvalidOperationException("Expected projected restore conflict receipts.");

        WorkspaceRestoreConflictReceiptProjection entitlementProjection = receipts.Single(item => string.Equals(item.ReceiptId, entitlementConflict.ReceiptId, StringComparison.Ordinal));
        WorkspaceRestoreConflictReceiptProjection workspaceProjection = receipts.Single(item => string.Equals(item.ReceiptId, workspaceConflict.ReceiptId, StringComparison.Ordinal));
        WorkspaceRestoreConflictReceiptProjection artifactDriftProjection = receipts.Single(item => string.Equals(item.ReceiptId, artifactDriftConflict.ReceiptId, StringComparison.Ordinal));

        VerificationAssert.True(
            entitlementProjection.Summary.Contains("Entitlement sync has a blocking restore conflict", StringComparison.Ordinal)
                && entitlementProjection.Summary.Contains("grant-orphan", StringComparison.Ordinal),
            "Entitlement-sync conflict receipts should recover a user-facing summary when source text is blank.");
        VerificationAssert.True(
            workspaceProjection.Summary.Contains("Workspace restore has a reviewable continuity conflict", StringComparison.Ordinal)
                && workspaceProjection.Summary.Contains("install-stale", StringComparison.Ordinal),
            "Workspace-restore conflict receipts should recover a user-facing summary when source text is blank.");
        VerificationAssert.True(
            string.Equals(entitlementProjection.Resolution, "Open account access and resolve this restore receipt before continuing on this workspace.", StringComparison.Ordinal),
            "Blocking blank-summary conflict receipts should still carry the standard recovery action.");
        VerificationAssert.True(
            string.Equals(entitlementProjection.Severity, "blocking", StringComparison.Ordinal),
            "Blocking restore conflict receipts should project blocking severity even when source severity was softer.");
        VerificationAssert.True(
            string.Equals(entitlementProjection.ConflictPosture, "blocking_conflict", StringComparison.Ordinal)
                && string.Equals(entitlementProjection.RecoverabilityPosture, "recoverable_by_account_access_before_continue", StringComparison.Ordinal),
            "Blocking entitlement-sync conflict receipts should expose normalized conflict and recoverability posture.");
        VerificationAssert.True(
            string.Equals(entitlementProjection.Authority, "hub_entitlement_ledger", StringComparison.Ordinal),
            "Entitlement-sync conflict receipts should name the entitlement ledger authority plane.");
        VerificationAssert.True(
            string.Equals(workspaceProjection.Authority, "hub_registry_install_linking", StringComparison.Ordinal),
            "Workspace restore claimed-installation conflicts should name the install-linking authority plane.");
        VerificationAssert.True(
            string.Equals(artifactDriftProjection.Authority, "hub_registry_release_receipts", StringComparison.Ordinal)
                && string.Equals(artifactDriftProjection.RecoveryRoute, "/downloads", StringComparison.Ordinal)
                && artifactDriftProjection.RecoveryHint.Contains("signed-in download or install rail", StringComparison.Ordinal),
            "Artifact-drift conflict receipts should recover through the downloads rail that owns release artifact truth.");
    }

    private static void VerifyServerPlaneConflictReceiptsRecoverBlankIdentityFields()
    {
        MethodInfo projectMethod = typeof(CampaignWorkspaceServerPlaneService).GetMethod(
            "ProjectRestoreConflictReceipts",
            BindingFlags.NonPublic | BindingFlags.Static)
            ?? throw new InvalidOperationException("Expected server-plane restore conflict projection method.");

        WorkspaceRestoreConflictReceipt blankIdentityConflict = new(
            ReceiptId: " ",
            Severity: "",
            Kind: null!,
            SubjectId: " ",
            Summary: "",
            Resolution: null,
            ObservedAtUtc: DateTimeOffset.UtcNow,
            Surface: "entitlement_sync",
            BlocksContinue: true);

        object? projected = projectMethod.Invoke(
            null,
            [new[] { blankIdentityConflict }]);
        IReadOnlyList<WorkspaceRestoreConflictReceiptProjection> receipts =
            projected as IReadOnlyList<WorkspaceRestoreConflictReceiptProjection>
            ?? throw new InvalidOperationException("Expected projected restore conflict receipts.");
        WorkspaceRestoreConflictReceiptProjection receipt = receipts.Single();

        VerificationAssert.True(
            string.Equals(receipt.ReceiptId, "entitlement_sync:entitlement_restore_conflict:unknown_restore_subject:conflict", StringComparison.Ordinal),
            "Blank restore conflict receipt ids should recover a deterministic surface, kind, and subject receipt id.");
        VerificationAssert.True(
            string.Equals(receipt.Severity, "blocking", StringComparison.Ordinal),
            "Blank blocking restore conflict severities should recover explicit blocking posture.");
        VerificationAssert.True(
            string.Equals(receipt.RecoveryRoute, "/account/access", StringComparison.Ordinal),
            "Blank blocking entitlement restore conflicts should recover the account access route.");
        VerificationAssert.True(
            receipt.RecoveryHint.Contains("Open account access", StringComparison.Ordinal)
                && receipt.RecoveryHint.Contains("unknown restore subject", StringComparison.Ordinal),
            "Blank blocking entitlement restore conflicts should recover a concrete account-access recovery hint.");
        VerificationAssert.True(
            string.Equals(receipt.ContinuePosture, "blocked_until_receipt_resolved", StringComparison.Ordinal),
            "Blank blocking restore conflict projections should expose a blocked-until-resolved continue posture.");
        VerificationAssert.True(
            string.Equals(receipt.ConflictPosture, "blocking_conflict", StringComparison.Ordinal)
                && string.Equals(receipt.RecoverabilityPosture, "recoverable_by_account_access_before_continue", StringComparison.Ordinal),
            "Blank blocking restore conflict projections should recover normalized conflict and account-access recoverability posture.");
        VerificationAssert.True(
            string.Equals(receipt.Kind, "entitlement_restore_conflict", StringComparison.Ordinal),
            "Blank entitlement restore conflict kinds should recover an entitlement-sync conflict kind.");
        VerificationAssert.True(
            string.Equals(receipt.SubjectId, "unknown restore subject", StringComparison.Ordinal),
            "Blank restore conflict subjects should recover an explicit unknown-subject posture.");
        VerificationAssert.True(
            receipt.Summary.Contains("unknown restore subject", StringComparison.Ordinal),
            "Recovered blank-subject restore conflict summaries should name the unknown restore subject.");
    }

    private static void VerifyServerPlaneBlankArtifactDriftConflictsRecoverDownloadResolution()
    {
        MethodInfo projectMethod = typeof(CampaignWorkspaceServerPlaneService).GetMethod(
            "ProjectRestoreConflictReceipts",
            BindingFlags.NonPublic | BindingFlags.Static)
            ?? throw new InvalidOperationException("Expected server-plane restore conflict projection method.");

        WorkspaceRestoreConflictReceipt blankArtifactDriftConflict = new(
            ReceiptId: "receipt-blank-artifact-drift",
            Severity: "attention",
            Kind: "entitlement_artifact_drift",
            SubjectId: "artifact-drift",
            Summary: "Artifact receipt drift blocks restore replay.",
            Resolution: " ",
            ObservedAtUtc: DateTimeOffset.UtcNow,
            Surface: "entitlement_sync",
            BlocksContinue: true);

        IReadOnlyList<WorkspaceRestoreConflictReceiptProjection> receipts =
            projectMethod.Invoke(null, [new[] { blankArtifactDriftConflict }]) as IReadOnlyList<WorkspaceRestoreConflictReceiptProjection>
            ?? throw new InvalidOperationException("Expected projected restore conflict receipts.");
        WorkspaceRestoreConflictReceiptProjection receipt = receipts.Single();

        VerificationAssert.True(
            string.Equals(receipt.RecoveryRoute, "/downloads", StringComparison.Ordinal)
                && string.Equals(receipt.Resolution, "Refresh the signed-in download or install rail before continuing on this workspace.", StringComparison.Ordinal),
            "Blank blocking artifact-drift conflicts should recover a downloads/install-rail resolution instead of the account-access entitlement fallback.");
        VerificationAssert.True(
            string.Equals(receipt.Authority, "hub_registry_release_receipts", StringComparison.Ordinal)
                && string.Equals(receipt.RecoverabilityPosture, "recoverable_by_download_refresh_before_continue", StringComparison.Ordinal),
            "Blank blocking artifact-drift conflicts should stay bound to release receipt authority and download-refresh recoverability.");
    }

    private static void VerifyServerPlaneBlockingSeverityControlsContinuePosture()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), "run-services-verification", "campaign-spine-restore-severity-posture", Guid.NewGuid().ToString("N"));
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
            WorkspaceLifecyclePolicyService lifecycle = new(configuration);
            CampaignSpineService campaignSpine = new(store, lifecycle, new CampaignArtifactRegistryBridge(store));
            HubUserDto user = accounts.EnsureUser("subject.restore.severity", "Gate", "gate@example.invalid");
            CampaignWorkspaceProjection workspace = campaignSpine.GetStarterWorkspace(user)
                ?? throw new InvalidOperationException("Expected a starter workspace.");

            WorkspaceRestoreConflictReceipt severityOnlyBlockingConflict = new(
                ReceiptId: "severity-only-blocking",
                Severity: "blocking",
                Kind: "entitlement_missing",
                SubjectId: "install-severity",
                Summary: "Blocking entitlement sync conflict.",
                Resolution: "Refresh account access before continuing.",
                ObservedAtUtc: DateTimeOffset.UtcNow,
                Surface: "entitlement_sync",
                BlocksContinue: false);
            WorkspaceRestoreProjection restore = new(
                RestoreId: "restore-severity",
                UserId: user.UserId,
                RecentDossiers: [],
                RecentCampaigns: [],
                RecentRuleEnvironments: [],
                RecentArtifacts: [],
                Entitlements: [],
                ClaimedDevices: [],
                ConflictSummaries: [],
                LocalOnlyNotes: [],
                GeneratedAtUtc: DateTimeOffset.UtcNow,
                ProvenanceReceipts: [],
                ConflictReceipts: [severityOnlyBlockingConflict]);

            MethodInfo projectMethod = typeof(CampaignWorkspaceServerPlaneService).GetMethod(
                "ProjectRestoreConflictReceipts",
                BindingFlags.NonPublic | BindingFlags.Static)
                ?? throw new InvalidOperationException("Expected server-plane restore conflict projection method.");
            IReadOnlyList<WorkspaceRestoreConflictReceiptProjection> receipts =
                projectMethod.Invoke(null, [new[] { severityOnlyBlockingConflict }]) as IReadOnlyList<WorkspaceRestoreConflictReceiptProjection>
                ?? throw new InvalidOperationException("Expected projected restore conflict receipts.");

            MethodInfo continuityMethod = typeof(CampaignWorkspaceServerPlaneService).GetMethod(
                "BuildContinuityConflicts",
                BindingFlags.NonPublic | BindingFlags.Static)
                ?? throw new InvalidOperationException("Expected server-plane continuity conflict method.");
            IReadOnlyList<ContinuityConflictCue> continuityCues =
                continuityMethod.Invoke(null, [workspace, restore]) as IReadOnlyList<ContinuityConflictCue>
                ?? throw new InvalidOperationException("Expected projected continuity conflict cues.");

            MethodInfo nextSafeActionMethod = typeof(CampaignWorkspaceServerPlaneService).GetMethod(
                "BuildNextSafeActionCue",
                BindingFlags.NonPublic | BindingFlags.Static)
                ?? throw new InvalidOperationException("Expected server-plane next-safe-action method.");
            NextSafeActionCue nextSafeAction =
                nextSafeActionMethod.Invoke(null, [workspace, restore, null, Array.Empty<SupportCaseDigestViewModel>()]) as NextSafeActionCue
                ?? throw new InvalidOperationException("Expected restore next-safe-action cue.");

            WorkspaceRestoreConflictReceiptProjection receipt = receipts.Single();
            VerificationAssert.True(
                receipt.BlocksContinue
                    && string.Equals(receipt.ContinuePosture, "blocked_until_receipt_resolved", StringComparison.Ordinal)
                    && string.Equals(receipt.Severity, "blocking", StringComparison.Ordinal)
                    && receipt.Summary.Contains("blocking restore conflict", StringComparison.Ordinal),
                "Blocking-severity restore conflict receipts should project blocked continuation even when source BlocksContinue is false.");
            VerificationAssert.True(
                continuityCues.Any(item =>
                    item.CueId.Contains("restore-conflict:", StringComparison.Ordinal)
                    && string.Equals(item.Severity, "blocking", StringComparison.Ordinal)),
                "Blocking-severity restore conflict receipts should render blocking continuity cues.");
            VerificationAssert.True(
                string.Equals(nextSafeAction.SourceKind, "restore", StringComparison.Ordinal)
                    && string.Equals(nextSafeAction.Label, "Review restore receipts", StringComparison.Ordinal),
                "Blocking-severity restore conflict receipts should drive the restore next-safe-action.");
        }
        finally
        {
            if (Directory.Exists(tempRoot))
            {
                Directory.Delete(tempRoot, recursive: true);
            }
        }
    }

    private static void VerifyServerPlanePrioritizesRecoverableConflictReceipts()
    {
        MethodInfo projectMethod = typeof(CampaignWorkspaceServerPlaneService).GetMethod(
            "ProjectRestoreConflictReceipts",
            BindingFlags.NonPublic | BindingFlags.Static)
            ?? throw new InvalidOperationException("Expected server-plane restore conflict projection method.");

        DateTimeOffset now = DateTimeOffset.UtcNow;
        WorkspaceRestoreConflictReceipt[] sourceReceipts =
        [
            new(
                ReceiptId: "workspace-summary-newer",
                Severity: "warning",
                Kind: "restore_summary_conflict",
                SubjectId: "restore-plane",
                Summary: "Generic workspace restore summary conflict.",
                Resolution: "Review generic restore posture.",
                ObservedAtUtc: now.AddMinutes(5),
                Surface: "workspace_restore",
                BlocksContinue: true),
            new(
                ReceiptId: "entitlement-stale-claim",
                Severity: "attention",
                Kind: "entitlement_replication_stale_claim",
                SubjectId: "grant-stale",
                Summary: "Entitlement replication points at stale claimed-install state.",
                Resolution: "Refresh account access before continuing.",
                ObservedAtUtc: now,
                Surface: "entitlement_sync",
                BlocksContinue: true),
            new(
                ReceiptId: "workspace-info",
                Severity: "info",
                Kind: "restore_artifact_missing",
                SubjectId: "install-missing-artifact",
                Summary: "Workspace restore is missing artifact evidence.",
                Resolution: "Refresh artifact evidence.",
                ObservedAtUtc: now.AddMinutes(10),
                Surface: "workspace_restore",
                BlocksContinue: false)
        ];

        object? projected = projectMethod.Invoke(null, [sourceReceipts]);
        IReadOnlyList<WorkspaceRestoreConflictReceiptProjection> receipts =
            projected as IReadOnlyList<WorkspaceRestoreConflictReceiptProjection>
            ?? throw new InvalidOperationException("Expected projected restore conflict receipts.");

        VerificationAssert.True(
            string.Equals(receipts[0].ReceiptId, "entitlement-stale-claim", StringComparison.Ordinal)
                && string.Equals(receipts[0].Surface, "entitlement_sync", StringComparison.Ordinal)
                && string.Equals(receipts[0].ContinuePosture, "blocked_until_receipt_resolved", StringComparison.Ordinal)
                && receipts[0].RecoveryHint.Contains("account access", StringComparison.OrdinalIgnoreCase),
            "Recoverable entitlement-sync blockers should sort ahead of generic workspace restore conflicts so receipt drawers cannot hide the account-access recovery path.");

        string tempRoot = Path.Combine(Path.GetTempPath(), "run-services-verification", "campaign-spine-restore-conflict-action-priority", Guid.NewGuid().ToString("N"));
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
            WorkspaceLifecyclePolicyService lifecycle = new(configuration);
            CampaignSpineService campaignSpine = new(store, lifecycle, new CampaignArtifactRegistryBridge(store));
            HubUserDto user = accounts.EnsureUser("subject.restore.conflict.priority", "Conflict", "conflict-priority@example.invalid");
            CampaignWorkspaceProjection workspace = campaignSpine.GetStarterWorkspace(user)
                ?? throw new InvalidOperationException("Expected a starter workspace.");
            WorkspaceRestoreProjection restore = new(
                RestoreId: "restore-conflict-action-priority",
                UserId: user.UserId,
                RecentDossiers: [],
                RecentCampaigns: [],
                RecentRuleEnvironments: [],
                RecentArtifacts: [],
                Entitlements: [],
                ClaimedDevices: [],
                ConflictSummaries: [],
                LocalOnlyNotes: [],
                GeneratedAtUtc: now,
                ProvenanceReceipts: [],
                ConflictReceipts: sourceReceipts);

            MethodInfo continuityMethod = typeof(CampaignWorkspaceServerPlaneService).GetMethod(
                "BuildContinuityConflicts",
                BindingFlags.NonPublic | BindingFlags.Static)
                ?? throw new InvalidOperationException("Expected server-plane continuity conflict method.");
            IReadOnlyList<ContinuityConflictCue> continuityCues =
                continuityMethod.Invoke(null, [workspace, restore]) as IReadOnlyList<ContinuityConflictCue>
                ?? throw new InvalidOperationException("Expected projected continuity conflict cues.");

            MethodInfo nextSafeActionMethod = typeof(CampaignWorkspaceServerPlaneService).GetMethod(
                "BuildNextSafeActionCue",
                BindingFlags.NonPublic | BindingFlags.Static)
                ?? throw new InvalidOperationException("Expected server-plane next-safe-action method.");
            NextSafeActionCue nextSafeAction =
                nextSafeActionMethod.Invoke(null, [workspace, restore, null, Array.Empty<SupportCaseDigestViewModel>()]) as NextSafeActionCue
                ?? throw new InvalidOperationException("Expected restore next-safe-action cue.");

            VerificationAssert.True(
                continuityCues.Count > 0
                    && string.Equals(continuityCues[0].ResolutionAction, "Refresh account access before continuing.", StringComparison.Ordinal),
                "Continuity conflict cues should use the same recoverability priority as receipt drawers so stale entitlement replication is not hidden behind generic workspace blockers.");
            VerificationAssert.True(
                string.Equals(nextSafeAction.Summary, "Refresh account access before continuing.", StringComparison.Ordinal),
                "Restore next-safe-action should select the highest-priority recoverable entitlement conflict instead of the first generic workspace blocker.");
        }
        finally
        {
            if (Directory.Exists(tempRoot))
            {
                Directory.Delete(tempRoot, recursive: true);
            }
        }
    }

    private static void VerifyClaimedDeviceRestoreSummariesNameExactPrefetchSet()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), "run-services-verification", "campaign-spine-restore", Guid.NewGuid().ToString("N"));
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
            WorkspaceLifecyclePolicyService lifecycle = new(configuration);
            CampaignSpineService campaignSpine = new(store, lifecycle, new CampaignArtifactRegistryBridge(store));

            HubUserDto user = accounts.EnsureUser("subject.restore", "Rook", "rook@example.invalid");
            DateTimeOffset now = DateTimeOffset.UtcNow;

            InstallLinkingSummaryDto installLinking = new(
                RecentReceipts:
                [
                    new DownloadReceiptDto(
                        ReceiptId: "receipt-travel",
                        ArtifactId: "artifact-travel-kit",
                        ArtifactLabel: "Android travel kit",
                        FileName: "travel-kit.apk",
                        DownloadUrl: "/downloads/files/travel-kit.apk",
                        Channel: "preview",
                        Version: "2026.03.29-preview.1",
                        Head: "pwa",
                        Platform: "android",
                        Arch: "arm64",
                        Kind: "portable",
                        InstallAccessClass: InstallAccessClasses.AccountRecommended,
                        IssuedAtUtc: now.AddMinutes(-10),
                        UserId: user.UserId,
                        SubjectId: user.SubjectId,
                        ClaimTicketId: null,
                        ClaimCode: null,
                        ClaimTicketExpiresAtUtc: null)
                ],
                PendingClaimTickets: Array.Empty<InstallClaimTicketDto>(),
                ClaimedInstallations:
                [
                    new ClaimedInstallationDto(
                        InstallationId: "install-tablet",
                        ArtifactId: "artifact-travel-kit",
                        Channel: "preview",
                        Version: "2026.03.29-preview.1",
                        InstallAccessClass: InstallAccessClasses.AccountRecommended,
                        Status: ClaimedInstallationStates.Active,
                        CreatedAtUtc: now.AddDays(-2),
                        UpdatedAtUtc: now.AddMinutes(-5),
                        UserId: user.UserId,
                        SubjectId: user.SubjectId,
                        PublicKey: "public-key-tablet",
                        ClaimTicketId: "ticket-tablet",
                        HeadId: "pwa",
                        Platform: "android",
                        Arch: "arm64",
                        HostLabel: "Travel tablet",
                        GrantId: "grant-tablet"),
                    new ClaimedInstallationDto(
                        InstallationId: "install-safehouse",
                        ArtifactId: "artifact-travel-kit",
                        Channel: "stable",
                        Version: "2026.03.29-stable.1",
                        InstallAccessClass: InstallAccessClasses.AccountRecommended,
                        Status: ClaimedInstallationStates.Active,
                        CreatedAtUtc: now.AddDays(-4),
                        UpdatedAtUtc: now.AddMinutes(-3),
                        UserId: user.UserId,
                        SubjectId: user.SubjectId,
                        PublicKey: "public-key-safehouse",
                        ClaimTicketId: "ticket-safehouse",
                        HeadId: "offline",
                        Platform: "linux",
                        Arch: "x64",
                        HostLabel: "Safehouse mirror",
                        GrantId: "grant-safehouse"),
                    new ClaimedInstallationDto(
                        InstallationId: "install-stale",
                        ArtifactId: "artifact-travel-kit",
                        Channel: "preview",
                        Version: "2026.03.29-preview.1",
                        InstallAccessClass: InstallAccessClasses.AccountRecommended,
                        Status: ClaimedInstallationStates.Active,
                        CreatedAtUtc: now.AddDays(-50),
                        UpdatedAtUtc: now.AddDays(-45),
                        UserId: user.UserId,
                        SubjectId: user.SubjectId,
                        PublicKey: "public-key-stale",
                        ClaimTicketId: "ticket-stale",
                        HeadId: "pwa",
                        Platform: "android",
                        Arch: "arm64",
                        HostLabel: "Stale travel tablet",
                        GrantId: "grant-stale")
                ],
                ActiveGrants:
                [
                    new InstallationGrantDto(
                        GrantId: "grant-tablet",
                        InstallationId: "install-tablet",
                        Status: InstallationGrantStates.Active,
                        AccessToken: "grant-tablet-token",
                        IssuedAtUtc: now.AddMinutes(-20),
                        ExpiresAtUtc: now.AddDays(7),
                        UserId: user.UserId,
                        SubjectId: user.SubjectId),
                    new InstallationGrantDto(
                        GrantId: "grant-safehouse",
                        InstallationId: "install-safehouse",
                        Status: InstallationGrantStates.Active,
                        AccessToken: "grant-safehouse-token",
                        IssuedAtUtc: now.AddMinutes(-18),
                        ExpiresAtUtc: now.AddDays(7),
                        UserId: user.UserId,
                        SubjectId: user.SubjectId),
                    new InstallationGrantDto(
                        GrantId: "grant-stale",
                        InstallationId: "install-stale",
                        Status: InstallationGrantStates.Active,
                        AccessToken: "grant-stale-token",
                        IssuedAtUtc: now.AddMinutes(-17),
                        ExpiresAtUtc: now.AddDays(7),
                        UserId: user.UserId,
                        SubjectId: user.SubjectId),
                    new InstallationGrantDto(
                        GrantId: "grant-orphan",
                        InstallationId: "install-orphan",
                        Status: InstallationGrantStates.Active,
                        AccessToken: "grant-orphan-token",
                        IssuedAtUtc: now.AddMinutes(-16),
                        ExpiresAtUtc: now.AddDays(7),
                        UserId: user.UserId,
                        SubjectId: user.SubjectId)
                ]);

            WorkspaceRestoreProjection restore = campaignSpine.GetRestoreProjection(user, installLinking);
            ClaimedDeviceRestoreProjection tablet = restore.ClaimedDevices.Single(device => string.Equals(device.InstallationId, "install-tablet", StringComparison.Ordinal));
            ClaimedDeviceRestoreProjection safehouse = restore.ClaimedDevices.Single(device => string.Equals(device.InstallationId, "install-safehouse", StringComparison.Ordinal));

            VerificationAssert.True(tablet.RestoreSummary.Contains("Exact set:", StringComparison.Ordinal), "Claimed-device restore summary should name the exact prefetch set for the play tablet lane.");
            VerificationAssert.True(tablet.RestoreSummary.Contains("Rook dossier", StringComparison.Ordinal), "Claimed-device restore summary should name the grounded dossier.");
            VerificationAssert.True(tablet.RestoreSummary.Contains("Rook preview campaign", StringComparison.Ordinal), "Claimed-device restore summary should name the grounded campaign.");
            VerificationAssert.True(tablet.RestoreSummary.Contains("sr6.preview.v1 [campaign-approved]", StringComparison.Ordinal), "Claimed-device restore summary should name the grounded rule environment.");
            VerificationAssert.True(tablet.RestoreSummary.Contains("Android travel kit (artifact-travel-kit)", StringComparison.Ordinal), "Claimed-device restore summary should name the grounded reconnectable artifact set.");
            VerificationAssert.True(safehouse.DeviceRole == "travel_cache", "Offline stable safehouse installs should project as travel-cache restore lanes.");
            VerificationAssert.True(safehouse.RestoreSummary.Contains("Travel-safe cache keeps", StringComparison.Ordinal), "Travel-cache restore summaries should stay explicit about safehouse posture.");
            VerificationAssert.True(safehouse.RestoreSummary.Contains("Exact set:", StringComparison.Ordinal), "Travel-cache restore summaries should also name the exact prefetch set.");

            VerificationAssert.True((restore.ProvenanceReceipts?.Count ?? 0) >= 3, "Restore projection should emit provenance receipts for entitlement, install, and rule-posture replay.");
            VerificationAssert.True(restore.ProvenanceReceipts?.Any(item => string.Equals(item.Kind, "claimed_installation", StringComparison.OrdinalIgnoreCase) && string.Equals(item.SubjectId, tablet.InstallationId, StringComparison.Ordinal)) == true,
                "Restore provenance should include each claimed device as a concrete receipt.");
            VerificationAssert.True(restore.ProvenanceReceipts?.Any(item => string.Equals(item.Kind, "active_entitlement", StringComparison.OrdinalIgnoreCase) && !string.IsNullOrWhiteSpace(item.Proof)) == true,
                "Entitlement replay should remain proof-bound in restore provenance receipts.");
            VerificationAssert.True(restore.ProvenanceReceipts?.Any(item =>
                    string.Equals(item.Kind, "entitlement_replication", StringComparison.OrdinalIgnoreCase)
                    && string.Equals(item.Surface, "entitlement_sync", StringComparison.Ordinal)
                    && string.Equals(item.Authority, "hub_entitlement_ledger", StringComparison.Ordinal)
                    && !string.IsNullOrWhiteSpace(item.Proof)
                    && item.Proof.Contains("matched:", StringComparison.Ordinal)
                    && item.Proof.Contains("orphaned:", StringComparison.Ordinal)) == true,
                "Entitlement replication should emit a ledger-authority provenance receipt with matched and orphaned grant counts.");
            VerificationAssert.True(restore.ProvenanceReceipts?.Any(item =>
                    string.Equals(item.Kind, "active_entitlement", StringComparison.OrdinalIgnoreCase)
                    && string.Equals(item.Authority, "hub_entitlement_ledger", StringComparison.Ordinal)
                    && !string.IsNullOrWhiteSpace(item.RecoveryHint)) == true,
                "Entitlement restore provenance should name the authority plane and a concrete recovery hint.");
            VerificationAssert.True(restore.ProvenanceReceipts?.Any(item =>
                    string.Equals(item.Kind, "entitlement_artifact_drift", StringComparison.OrdinalIgnoreCase)
                    && string.Equals(item.Surface, "entitlement_sync", StringComparison.Ordinal)
                    && string.Equals(item.Authority, "hub_registry_release_receipts", StringComparison.Ordinal)
                    && item.RecoveryHint.Contains("download or install rail", StringComparison.OrdinalIgnoreCase)) == true,
                "Artifact drift should emit entitlement-sync provenance so stale release truth is recoverable before continuation.");
            VerificationAssert.True(restore.ProvenanceReceipts?.Any(item =>
                    string.Equals(item.Kind, "claimed_installation_stale", StringComparison.OrdinalIgnoreCase)
                    && string.Equals(item.SubjectId, "install-stale", StringComparison.Ordinal)
                    && string.Equals(item.Surface, "workspace_restore", StringComparison.Ordinal)
                    && item.Proof.Contains("updated:", StringComparison.Ordinal)) == true,
                "Stale claimed installs should emit workspace-restore provenance with proof and recovery posture instead of only a conflict summary.");
            VerificationAssert.True(restore.ProvenanceReceipts?.Any(item =>
                    string.Equals(item.Kind, "entitlement_replication_stale_claim", StringComparison.OrdinalIgnoreCase)
                    && string.Equals(item.SubjectId, "grant-stale", StringComparison.Ordinal)
                    && string.Equals(item.Surface, "entitlement_sync", StringComparison.Ordinal)
                    && string.Equals(item.Authority, "hub_entitlement_ledger", StringComparison.Ordinal)) == true,
                "Entitlement replication should emit provenance when a grant is backed by stale claimed-install state.");
            VerificationAssert.True(restore.ProvenanceReceipts?.All(item => !string.IsNullOrWhiteSpace(item.Surface)) == true,
                "Restore provenance receipts should preserve an explicit workspace_restore or entitlement_sync surface.");
            VerificationAssert.True(restore.ProvenanceReceipts?.All(item => !string.IsNullOrWhiteSpace(item.Authority)) == true,
                "Restore provenance receipts should preserve the authority plane that issued the proof.");
            VerificationAssert.True(restore.ProvenanceReceipts?.All(item => !string.IsNullOrWhiteSpace(item.RecoveryHint)) == true,
                "Restore provenance receipts should preserve a concrete recovery hint for stale or disputed continuation.");
            VerificationAssert.True(restore.ConflictReceipts?.Any(item => string.Equals(item.Kind, "restore_summary_conflict", StringComparison.OrdinalIgnoreCase)) == true,
                "Restore conflicts should be emitted as structured receipts for review and recovery.");
            VerificationAssert.True(restore.ConflictReceipts?.Any(item => string.Equals(item.Kind, "entitlement_orphan", StringComparison.OrdinalIgnoreCase)) == true,
                "Restore conflicts should emit orphaned entitlement receipts when sync and claimed installs drift.");
            VerificationAssert.True(restore.ConflictReceipts?.All(item => !string.IsNullOrWhiteSpace(item.Surface)) == true,
                "Restore conflict receipts should preserve an explicit workspace_restore or entitlement_sync surface.");
            VerificationAssert.True(restore.ConflictReceipts?.Any(item =>
                    string.Equals(item.Kind, "entitlement_orphan", StringComparison.OrdinalIgnoreCase)
                    && string.Equals(item.Surface, "entitlement_sync", StringComparison.Ordinal)
                    && item.BlocksContinue) == true,
                "Entitlement drift receipts should stay explicitly classified under entitlement sync and block continue until resolved.");
        }
        finally
        {
            if (Directory.Exists(tempRoot))
            {
                Directory.Delete(tempRoot, recursive: true);
            }
        }
    }

    private static void VerifyAftermathArtifactMetadataSurvivesReload()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), "run-services-verification", "campaign-spine-aftermath-registry", Guid.NewGuid().ToString("N"));
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
            WorkspaceLifecyclePolicyService lifecycle = new(configuration);
            CampaignSpineService campaignSpine = new(store, lifecycle, new CampaignArtifactRegistryBridge(store));
            HubUserDto user = accounts.EnsureUser("subject.aftermath", "Switch", "switch@example.invalid");

            CampaignWorkspaceProjection workspace = campaignSpine.GetStarterWorkspace(user)
                ?? throw new InvalidOperationException("Expected a starter workspace.");
            RunProjection? run = workspace.Runs.FirstOrDefault();
            AftermathRecapPackageProjection package = campaignSpine.RecordAftermathRecapPackage(
                user,
                workspace,
                run,
                "session_recap",
                "Reload recap",
                "Governed recap package for reload proof.",
                [
                    $"Run scope: {run?.Title ?? workspace.CampaignName}.",
                    "Continuity: governed return lane remains attached to the same campaign spine.",
                    "Package kind: session_recap.",
                    "Active scene: no pinned scene."
                ]);

            CommunityStore reloadedStore = new(configuration, NullLogger<CommunityStore>.Instance);
            CampaignSpineService reloadedCampaignSpine = new(reloadedStore, new WorkspaceLifecyclePolicyService(configuration), new CampaignArtifactRegistryBridge(reloadedStore));
            CampaignWorkspaceProjection reloadedWorkspace = reloadedCampaignSpine.GetStarterWorkspace(user)
                ?? throw new InvalidOperationException("Expected a reloaded starter workspace.");
            AftermathRecapPackageProjection reloadedPackage = reloadedWorkspace.AftermathPackages?.FirstOrDefault(item => string.Equals(item.PackageId, package.PackageId, StringComparison.Ordinal))
                ?? throw new InvalidOperationException("Expected a reloaded aftermath package.");

            VerificationAssert.Equal(package.ArtifactId, reloadedPackage.ArtifactId, "Reloaded aftermath packages should preserve the registered artifact id.");
            VerificationAssert.True(string.Equals(reloadedPackage.ArtifactKind, "RecapPackage", StringComparison.Ordinal), "Reloaded aftermath packages should preserve the recap artifact kind.");
            VerificationAssert.True(string.Equals(reloadedPackage.ArtifactVisibility, "campaign-shared", StringComparison.Ordinal), "Reloaded aftermath packages should preserve campaign-shared visibility.");
            VerificationAssert.True(string.Equals(reloadedPackage.ArtifactTrustTier, "curated", StringComparison.Ordinal), "Reloaded aftermath packages should preserve curated trust posture.");
            VerificationAssert.True(!string.IsNullOrWhiteSpace(reloadedPackage.ProvenanceSummary), "Reloaded aftermath packages should preserve provenance summaries.");
            VerificationAssert.True(!string.IsNullOrWhiteSpace(reloadedPackage.AuditSummary), "Reloaded aftermath packages should preserve audit summaries.");
            VerificationAssert.True(reloadedPackage.EvidenceLines.Any(item => item.StartsWith("Registry artifact:", StringComparison.OrdinalIgnoreCase)), "Reloaded aftermath packages should preserve registry artifact evidence.");
        }
        finally
        {
            if (Directory.Exists(tempRoot))
            {
                Directory.Delete(tempRoot, recursive: true);
            }
        }
    }

    private static void VerifyRestoreConflictReceiptsCaptureStaleClaimAndEntitlementState()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), "run-services-verification", "campaign-spine-restore-stale-state", Guid.NewGuid().ToString("N"));
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
            WorkspaceLifecyclePolicyService lifecycle = new(configuration);
            CampaignSpineService campaignSpine = new(store, lifecycle, new CampaignArtifactRegistryBridge(store));

            HubUserDto user = accounts.EnsureUser("subject.restore.stale", "Switch", "switch@example.invalid");
            DateTimeOffset now = DateTimeOffset.UtcNow;

            InstallLinkingSummaryDto installLinking = new(
                RecentReceipts:
                [
                    new DownloadReceiptDto(
                        ReceiptId: "receipt-stale",
                        ArtifactId: "artifact-stale",
                        ArtifactLabel: "Stale desktop payload",
                        FileName: "stale-linux.deb",
                        DownloadUrl: "/downloads/files/stale-linux.deb",
                        Channel: "preview",
                        Version: "2026.02.01-preview.1",
                        Head: "avalonia",
                        Platform: "linux",
                        Arch: "x64",
                        Kind: "installer",
                        InstallAccessClass: InstallAccessClasses.AccountRecommended,
                        IssuedAtUtc: now.AddDays(-45),
                        UserId: user.UserId,
                        SubjectId: user.SubjectId,
                        ClaimTicketId: null,
                        ClaimCode: null,
                        ClaimTicketExpiresAtUtc: null)
                ],
                PendingClaimTickets: Array.Empty<InstallClaimTicketDto>(),
                ClaimedInstallations:
                [
                    new ClaimedInstallationDto(
                        InstallationId: "install-stale",
                        ArtifactId: "artifact-stale",
                        Channel: "preview",
                        Version: "2026.02.01-preview.1",
                        InstallAccessClass: InstallAccessClasses.AccountRecommended,
                        Status: ClaimedInstallationStates.Revoked,
                        CreatedAtUtc: now.AddDays(-45),
                        UpdatedAtUtc: now.AddDays(-40),
                        UserId: user.UserId,
                        SubjectId: user.SubjectId,
                        PublicKey: "public-key-stale",
                        ClaimTicketId: "ticket-stale",
                        HeadId: "avalonia",
                        Platform: "linux",
                        Arch: "x64",
                        HostLabel: "Stale workstation",
                        GrantId: "grant-stale")
                ],
                ActiveGrants:
                [
                    new InstallationGrantDto(
                        GrantId: "grant-stale",
                        InstallationId: "install-stale",
                        Status: InstallationGrantStates.Expired,
                        AccessToken: "grant-stale-token",
                        IssuedAtUtc: now.AddDays(-45),
                        ExpiresAtUtc: now.AddDays(-15),
                        UserId: user.UserId,
                        SubjectId: user.SubjectId)
                ]);

            WorkspaceRestoreProjection restore = campaignSpine.GetRestoreProjection(user, installLinking);

            VerificationAssert.True(
                restore.ConflictSummaries.Any(item => item.Contains("stale or expired grants", StringComparison.OrdinalIgnoreCase)),
                "Restore conflict summaries should call out stale entitlement replay posture.");
            VerificationAssert.True(
                restore.ConflictSummaries.Any(item => item.Contains("stale or inactive device state", StringComparison.OrdinalIgnoreCase)),
                "Restore conflict summaries should call out stale claimed-install posture.");
            VerificationAssert.True(
                restore.ConflictReceipts?.Any(item => string.Equals(item.Kind, "entitlement_expired", StringComparison.OrdinalIgnoreCase)) == true,
                "Restore conflicts should emit explicit entitlement-expired receipts.");
            VerificationAssert.True(
                restore.ConflictReceipts?.Any(item => string.Equals(item.Kind, "entitlement_status_mismatch", StringComparison.OrdinalIgnoreCase)) == true,
                "Restore conflicts should emit explicit entitlement-status-mismatch receipts.");
            VerificationAssert.True(
                restore.ConflictReceipts?.Any(item => string.Equals(item.Kind, "claimed_installation_inactive", StringComparison.OrdinalIgnoreCase)) == true,
                "Restore conflicts should emit explicit claimed-installation-inactive receipts.");
            VerificationAssert.True(
                restore.ConflictReceipts?.Any(item => string.Equals(item.Kind, "claimed_installation_stale", StringComparison.OrdinalIgnoreCase)) == true,
                "Restore conflicts should emit explicit claimed-installation-stale receipts.");
            VerificationAssert.True(
                restore.ConflictReceipts?.Any(item =>
                    string.Equals(item.Kind, "entitlement_replication_stale_claim", StringComparison.OrdinalIgnoreCase)
                    && string.Equals(item.Surface, "entitlement_sync", StringComparison.Ordinal)
                    && item.BlocksContinue) == true,
                "Entitlement replication should emit a blocking entitlement-sync conflict when a grant points at stale or inactive claimed installation state.");
            VerificationAssert.True(
                restore.ConflictReceipts?.Any(item =>
                    string.Equals(item.Kind, "claimed_installation_stale", StringComparison.OrdinalIgnoreCase)
                    && string.Equals(item.Severity, "blocking", StringComparison.OrdinalIgnoreCase)
                    && item.BlocksContinue) == true,
                "Stale claimed-install receipts should block continue until account-access relink refreshes restore evidence.");
        }
        finally
        {
            if (Directory.Exists(tempRoot))
            {
                Directory.Delete(tempRoot, recursive: true);
            }
        }
    }

    private static void VerifyRestoreConflictReceiptsCaptureDuplicateEntitlementReplication()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), "run-services-verification", "campaign-spine-restore-duplicate-entitlements", Guid.NewGuid().ToString("N"));
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
            WorkspaceLifecyclePolicyService lifecycle = new(configuration);
            CampaignSpineService campaignSpine = new(store, lifecycle, new CampaignArtifactRegistryBridge(store));

            HubUserDto user = accounts.EnsureUser("subject.restore.duplicate-entitlements", "Mirror", "mirror@example.invalid");
            DateTimeOffset now = DateTimeOffset.UtcNow;

            InstallLinkingSummaryDto installLinking = new(
                RecentReceipts:
                [
                    new DownloadReceiptDto(
                        ReceiptId: "receipt-duplicate",
                        ArtifactId: "artifact-duplicate",
                        ArtifactLabel: "Duplicate grant desktop payload",
                        FileName: "duplicate-linux.deb",
                        DownloadUrl: "/downloads/files/duplicate-linux.deb",
                        Channel: "preview",
                        Version: "2026.04.01-preview.1",
                        Head: "avalonia",
                        Platform: "linux",
                        Arch: "x64",
                        Kind: "installer",
                        InstallAccessClass: InstallAccessClasses.AccountRecommended,
                        IssuedAtUtc: now.AddMinutes(-30),
                        UserId: user.UserId,
                        SubjectId: user.SubjectId,
                        ClaimTicketId: null,
                        ClaimCode: null,
                        ClaimTicketExpiresAtUtc: null)
                ],
                PendingClaimTickets: Array.Empty<InstallClaimTicketDto>(),
                ClaimedInstallations:
                [
                    new ClaimedInstallationDto(
                        InstallationId: "install-duplicate",
                        ArtifactId: "artifact-duplicate",
                        Channel: "preview",
                        Version: "2026.04.01-preview.1",
                        InstallAccessClass: InstallAccessClasses.AccountRecommended,
                        Status: ClaimedInstallationStates.Active,
                        CreatedAtUtc: now.AddDays(-1),
                        UpdatedAtUtc: now.AddMinutes(-3),
                        UserId: user.UserId,
                        SubjectId: user.SubjectId,
                        PublicKey: "public-key-duplicate",
                        ClaimTicketId: "ticket-duplicate",
                        HeadId: "avalonia",
                        Platform: "linux",
                        Arch: "x64",
                        HostLabel: "Duplicate grant workstation",
                        GrantId: "grant-duplicate-a")
                ],
                ActiveGrants:
                [
                    new InstallationGrantDto(
                        GrantId: "grant-duplicate-a",
                        InstallationId: "install-duplicate",
                        Status: InstallationGrantStates.Active,
                        AccessToken: "grant-duplicate-a-token",
                        IssuedAtUtc: now.AddMinutes(-20),
                        ExpiresAtUtc: now.AddDays(7),
                        UserId: user.UserId,
                        SubjectId: user.SubjectId),
                    new InstallationGrantDto(
                        GrantId: "grant-duplicate-b",
                        InstallationId: "install-duplicate",
                        Status: InstallationGrantStates.Active,
                        AccessToken: "grant-duplicate-b-token",
                        IssuedAtUtc: now.AddMinutes(-18),
                        ExpiresAtUtc: now.AddDays(7),
                        UserId: user.UserId,
                        SubjectId: user.SubjectId)
                ]);

            WorkspaceRestoreProjection restore = campaignSpine.GetRestoreProjection(user, installLinking);
            WorkspaceRestoreConflictReceipt duplicateConflict = restore.ConflictReceipts?.Single(item =>
                string.Equals(item.Kind, "entitlement_replication_duplicate_grant", StringComparison.OrdinalIgnoreCase))
                ?? throw new InvalidOperationException("Expected duplicate entitlement replication conflict receipt.");

            VerificationAssert.True(
                string.Equals(duplicateConflict.Surface, "entitlement_sync", StringComparison.Ordinal)
                    && string.Equals(duplicateConflict.Severity, "blocking", StringComparison.OrdinalIgnoreCase)
                    && duplicateConflict.BlocksContinue,
                "Duplicate active entitlement grants for one claimed install should emit a blocking entitlement-sync conflict receipt.");
            VerificationAssert.True(
                duplicateConflict.Summary.Contains("grant-duplicate-a", StringComparison.Ordinal)
                    && duplicateConflict.Summary.Contains("grant-duplicate-b", StringComparison.Ordinal)
                    && duplicateConflict.Resolution?.Contains("rotate duplicate entitlement grants", StringComparison.Ordinal) == true,
                "Duplicate entitlement replication receipts should name every competing grant and the account-access recovery action.");

            MethodInfo projectMethod = typeof(CampaignWorkspaceServerPlaneService).GetMethod(
                "ProjectRestoreConflictReceipts",
                BindingFlags.NonPublic | BindingFlags.Static)
                ?? throw new InvalidOperationException("Expected server-plane restore conflict projection method.");
            IReadOnlyList<WorkspaceRestoreConflictReceiptProjection> projected =
                projectMethod.Invoke(null, [new[] { duplicateConflict }]) as IReadOnlyList<WorkspaceRestoreConflictReceiptProjection>
                ?? throw new InvalidOperationException("Expected projected duplicate entitlement conflict receipt.");
            WorkspaceRestoreConflictReceiptProjection projection = projected.Single();

            VerificationAssert.True(
                string.Equals(projection.Authority, "hub_entitlement_ledger", StringComparison.Ordinal)
                    && string.Equals(projection.RecoveryRoute, "/account/access", StringComparison.Ordinal)
                    && string.Equals(projection.ContinuePosture, "blocked_until_receipt_resolved", StringComparison.Ordinal)
                    && string.Equals(projection.ConflictPosture, "blocking_conflict", StringComparison.Ordinal)
                    && string.Equals(projection.RecoverabilityPosture, "recoverable_by_account_access_before_continue", StringComparison.Ordinal)
                    && projection.RecoveryHint.Contains("refresh entitlement replication", StringComparison.Ordinal),
                "Duplicate entitlement replication conflicts should remain recoverable through account access on the server plane.");
            VerificationAssert.True(
                projection.RecoverySummary.Contains("/account/access", StringComparison.Ordinal)
                    && projection.RecoverySummary.Contains("before continuing", StringComparison.OrdinalIgnoreCase)
                    && projection.RecoverySummary.Contains(duplicateConflict.SubjectId, StringComparison.Ordinal),
                "Duplicate entitlement replication conflict summaries should name the account-access route, subject, and blocked continuation posture.");
        }
        finally
        {
            if (Directory.Exists(tempRoot))
            {
                Directory.Delete(tempRoot, recursive: true);
            }
        }
    }

    private static void VerifyRestoreReceiptsSurviveCommunityStoreReload()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), "run-services-verification", "campaign-spine-restore-reload", Guid.NewGuid().ToString("N"));
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
            WorkspaceLifecyclePolicyService lifecycle = new(configuration);
            CampaignSpineService campaignSpine = new(store, lifecycle, new CampaignArtifactRegistryBridge(store));

            HubUserDto user = accounts.EnsureUser("subject.restore.reload", "Relay", "relay@example.invalid");
            DateTimeOffset now = DateTimeOffset.UtcNow;

            InstallLinkingSummaryDto installLinking = new(
                RecentReceipts:
                [
                    new DownloadReceiptDto(
                        ReceiptId: "receipt-reload",
                        ArtifactId: "artifact-reload",
                        ArtifactLabel: "Reload desktop payload",
                        FileName: "reload-linux.deb",
                        DownloadUrl: "/downloads/files/reload-linux.deb",
                        Channel: "preview",
                        Version: "2026.04.14-preview.1",
                        Head: "avalonia",
                        Platform: "linux",
                        Arch: "x64",
                        Kind: "installer",
                        InstallAccessClass: InstallAccessClasses.AccountRecommended,
                        IssuedAtUtc: now.AddMinutes(-30),
                        UserId: user.UserId,
                        SubjectId: user.SubjectId,
                        ClaimTicketId: null,
                        ClaimCode: null,
                        ClaimTicketExpiresAtUtc: null)
                ],
                PendingClaimTickets: Array.Empty<InstallClaimTicketDto>(),
                ClaimedInstallations:
                [
                    new ClaimedInstallationDto(
                        InstallationId: "install-reload",
                        ArtifactId: "artifact-reload",
                        Channel: "preview",
                        Version: "2026.04.14-preview.1",
                        InstallAccessClass: InstallAccessClasses.AccountRecommended,
                        Status: ClaimedInstallationStates.Active,
                        CreatedAtUtc: now.AddDays(-3),
                        UpdatedAtUtc: now.AddDays(-2),
                        UserId: user.UserId,
                        SubjectId: user.SubjectId,
                        PublicKey: "public-key-reload",
                        ClaimTicketId: "ticket-reload",
                        HeadId: "avalonia",
                        Platform: "linux",
                        Arch: "x64",
                        HostLabel: "Reload workstation",
                        GrantId: "grant-reload"),
                    new ClaimedInstallationDto(
                        InstallationId: "install-stale-reload",
                        ArtifactId: "artifact-reload-stale",
                        Channel: "stable",
                        Version: "2026.03.01-stable.1",
                        InstallAccessClass: InstallAccessClasses.AccountRecommended,
                        Status: ClaimedInstallationStates.Revoked,
                        CreatedAtUtc: now.AddDays(-45),
                        UpdatedAtUtc: now.AddDays(-40),
                        UserId: user.UserId,
                        SubjectId: user.SubjectId,
                        PublicKey: "public-key-reload-stale",
                        ClaimTicketId: "ticket-reload-stale",
                        HeadId: "avalonia",
                        Platform: "linux",
                        Arch: "x64",
                        HostLabel: "Stale reload workstation",
                        GrantId: "grant-reload-stale")
                ],
                ActiveGrants:
                [
                    new InstallationGrantDto(
                        GrantId: "grant-reload",
                        InstallationId: "install-reload",
                        Status: InstallationGrantStates.Active,
                        AccessToken: "grant-reload-token",
                        IssuedAtUtc: now.AddMinutes(-25),
                        ExpiresAtUtc: now.AddDays(7),
                        UserId: user.UserId,
                        SubjectId: user.SubjectId),
                    new InstallationGrantDto(
                        GrantId: "grant-reload-orphan",
                        InstallationId: "install-reload-orphan",
                        Status: InstallationGrantStates.Active,
                        AccessToken: "grant-reload-orphan-token",
                        IssuedAtUtc: now.AddMinutes(-20),
                        ExpiresAtUtc: now.AddDays(7),
                        UserId: user.UserId,
                        SubjectId: user.SubjectId)
                ]);

            WorkspaceRestoreProjection restore = campaignSpine.GetRestoreProjection(user, installLinking);
            VerificationAssert.True((restore.ProvenanceReceipts?.Count ?? 0) > 0, "Reload proof requires persisted restore provenance receipts.");
            VerificationAssert.True((restore.ConflictReceipts?.Count ?? 0) > 0, "Reload proof requires persisted restore conflict receipts.");

            CommunityStore reloadedStore = new(configuration, NullLogger<CommunityStore>.Instance);
            VerificationAssert.True(reloadedStore.RestoreByUserId.TryGetValue(user.UserId, out WorkspaceRestoreProjection? reloadedRestore), "Restore projections should survive community-store reload.");
            VerificationAssert.NotNull(reloadedRestore, "Reloaded restore projection should be available for receipt assertions.");

            WorkspaceRestoreProvenanceReceipt? entitlementReceipt = reloadedRestore!.ProvenanceReceipts?
                .FirstOrDefault(item => string.Equals(item.Kind, "active_entitlement", StringComparison.OrdinalIgnoreCase));
            VerificationAssert.NotNull(entitlementReceipt, "Reloaded restore projection should keep active-entitlement provenance receipts.");
            VerificationAssert.True(string.Equals(entitlementReceipt!.Authority, "hub_entitlement_ledger", StringComparison.Ordinal), "Reloaded entitlement provenance should preserve its authority plane.");
            VerificationAssert.True(!string.IsNullOrWhiteSpace(entitlementReceipt.RecoveryHint), "Reloaded entitlement provenance should preserve the recovery hint.");

            WorkspaceRestoreConflictReceipt? orphanConflict = reloadedRestore.ConflictReceipts?
                .FirstOrDefault(item => string.Equals(item.Kind, "entitlement_orphan", StringComparison.OrdinalIgnoreCase));
            VerificationAssert.NotNull(orphanConflict, "Reloaded restore projection should keep entitlement orphan conflict receipts.");
            VerificationAssert.True(string.Equals(orphanConflict!.Surface, "entitlement_sync", StringComparison.Ordinal), "Reloaded entitlement orphan conflicts should preserve entitlement-sync surface classification.");
            VerificationAssert.True(orphanConflict.BlocksContinue, "Reloaded entitlement orphan conflicts should preserve block-continue posture.");

            WorkspaceRestoreConflictReceipt? inactiveInstallConflict = reloadedRestore.ConflictReceipts?
                .FirstOrDefault(item => string.Equals(item.Kind, "claimed_installation_inactive", StringComparison.OrdinalIgnoreCase));
            VerificationAssert.NotNull(inactiveInstallConflict, "Reloaded restore projection should keep claimed-installation conflict receipts.");
            VerificationAssert.True(string.Equals(inactiveInstallConflict!.Surface, "workspace_restore", StringComparison.Ordinal), "Reloaded claimed-installation conflicts should preserve workspace-restore surface classification.");
        }
        finally
        {
            if (Directory.Exists(tempRoot))
            {
                Directory.Delete(tempRoot, recursive: true);
            }
        }
    }

    private sealed class DisabledEmailHandler : HttpMessageHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
            => Task.FromResult(new HttpResponseMessage(System.Net.HttpStatusCode.OK)
            {
                Content = JsonContent.Create(new { status = "disabled" })
            });
    }
}
