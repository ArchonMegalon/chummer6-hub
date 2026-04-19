using System.IO;
using Chummer.Campaign.Contracts;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Contracts.Community;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;

namespace RunServicesVerification;

internal static class WorkspaceLifecycleRetentionVerification
{
    public static Task RunAsync()
    {
        VerifyWorkspaceRetentionRunbook();
        VerifyExpiredRestoreSummariesArePrunedAndRegenerated();
        VerifyUnchangedRestoreProjectionPreservesReceiptObservationTimestamps();
        VerifyDuplicateSemanticReceiptsPreserveEarliestObservationTimestamps();
        return Task.CompletedTask;
    }

    private static void VerifyWorkspaceRetentionRunbook()
    {
        string runbookPath = Path.Combine(ResolveRepoRoot(), "docs", "HOSTED_WORKSPACE_RETENTION_RUNBOOK.md");
        string runbook = File.ReadAllText(runbookPath);

        VerificationAssert.True(runbook.Contains("RestoreByUserId", StringComparison.Ordinal), "Workspace retention runbook should name the restore-summary storage lane.");
        VerificationAssert.True(runbook.Contains("CHUMMER_WORKSPACE_RESTORE_RETENTION_DAYS", StringComparison.Ordinal), "Workspace retention runbook should document the retention override knob.");
        VerificationAssert.True(runbook.Contains("does not rewrite the durable store again", StringComparison.Ordinal), "Workspace retention runbook should define deterministic post-cleanup verification.");
    }

    private static void VerifyExpiredRestoreSummariesArePrunedAndRegenerated()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), "run-services-verification", "workspace-retention", Guid.NewGuid().ToString("N"));
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

            HubUserDto activeUser = accounts.EnsureUser("subject.retention", "Retention Runner", "runner@example.invalid");

            lock (store.Gate)
            {
                store.RestoreByUserId[activeUser.UserId] = BuildRestoreProjection(activeUser.UserId, DateTimeOffset.UtcNow.AddDays(-60));
                store.RestoreByUserId["usr_orphan"] = BuildRestoreProjection("usr_orphan", DateTimeOffset.UtcNow.AddDays(-90));
                store.PersistLocked();
            }

            AccountCampaignSummary firstSummary = campaignSpine.GetAccountSummary(activeUser);
            VerificationAssert.True(firstSummary.Restore.GeneratedAtUtc > DateTimeOffset.UtcNow.AddMinutes(-1), "Active users should receive a freshly regenerated restore summary after stale cleanup.");

            lock (store.Gate)
            {
                VerificationAssert.True(!store.RestoreByUserId.ContainsKey("usr_orphan"), "Orphaned restore summaries should be pruned during lifecycle cleanup.");
                VerificationAssert.NotNull(store.RestoreByUserId.GetValueOrDefault(activeUser.UserId), "The active user's restore summary should be rehydrated into the durable store.");
            }

            string firstStoreSnapshot = File.ReadAllText(store.StoragePath);
            DateTimeOffset regeneratedAtUtc = firstSummary.Restore.GeneratedAtUtc;

            AccountCampaignSummary secondSummary = campaignSpine.GetAccountSummary(activeUser);
            string secondStoreSnapshot = File.ReadAllText(store.StoragePath);

            VerificationAssert.Equal(
                regeneratedAtUtc.ToString("O"),
                secondSummary.Restore.GeneratedAtUtc.ToString("O"),
                "Unchanged workspace reads should preserve the existing restore summary timestamp.");
            VerificationAssert.Equal(firstStoreSnapshot, secondStoreSnapshot, "Unchanged workspace reads should not rewrite the community store.");
        }
        finally
        {
            if (Directory.Exists(tempRoot))
            {
                Directory.Delete(tempRoot, recursive: true);
            }
        }
    }

    private static WorkspaceRestoreProjection BuildRestoreProjection(string userId, DateTimeOffset generatedAtUtc)
        => new(
            RestoreId: $"restore::{userId}",
            UserId: userId,
            RecentDossiers: Array.Empty<RunnerDossierProjection>(),
            RecentCampaigns: Array.Empty<CampaignProjection>(),
            RecentRuleEnvironments:
            [
                new RuleEnvironmentRef(
                    EnvironmentId: $"ruleenv::{userId}",
                    OwnerScope: "person",
                    CompatibilityFingerprint: "sr6.preview.v1",
                    ApprovalState: "self_service",
                    SourcePacks: ["shadowrun-6e-core@current"],
                    HouseRulePacks: Array.Empty<string>(),
                    OptionToggles: ["explain_everywhere"])
            ],
            RecentArtifacts: Array.Empty<RestoreArtifactProjection>(),
            Entitlements: Array.Empty<RestoreEntitlementProjection>(),
            ClaimedDevices: Array.Empty<ClaimedDeviceRestoreProjection>(),
            ConflictSummaries: ["stale restore packet"],
            LocalOnlyNotes: ["local cache stays local"],
            GeneratedAtUtc: generatedAtUtc);

    private static void VerifyUnchangedRestoreProjectionPreservesReceiptObservationTimestamps()
    {
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_WORKSPACE_RESTORE_RETENTION_DAYS"] = "30"
            })
            .Build();

        WorkspaceLifecyclePolicyService lifecycle = new(configuration);
        DateTimeOffset baselineGeneratedAtUtc = DateTimeOffset.UtcNow.AddHours(-12);
        DateTimeOffset baselineObservedAtUtc = baselineGeneratedAtUtc.AddMinutes(5);

        WorkspaceRestoreProjection existing = BuildRestoreProjection("usr_receipt", baselineGeneratedAtUtc) with
        {
            ProvenanceReceipts =
            [
                new WorkspaceRestoreProvenanceReceipt(
                    ReceiptId: "restore-provenance:claimed-install",
                    Kind: "claimed_installation",
                    SubjectId: "install-01",
                    Surface: "workspace_restore",
                    Summary: "Restore packet retains the claimed install lane.",
                    Proof: "artifact:avalonia-linux",
                    ObservedAtUtc: baselineObservedAtUtc),
                new WorkspaceRestoreProvenanceReceipt(
                    ReceiptId: " ",
                    Kind: null!,
                    SubjectId: "",
                    Surface: "entitlement_sync",
                    Summary: "Entitlement restore provenance is recoverable even without a source receipt id.",
                    Proof: null,
                    ObservedAtUtc: baselineObservedAtUtc.AddMinutes(1)),
                new WorkspaceRestoreProvenanceReceipt(
                    ReceiptId: "restore-provenance:rotating-source-id:old",
                    Kind: "entitlement_replication_stale_claim",
                    SubjectId: "grant-rotating",
                    Surface: "entitlement_sync",
                    Summary: "Rotating source ids should still preserve first observation by semantic receipt identity.",
                    Proof: "grant-rotating",
                    ObservedAtUtc: baselineObservedAtUtc.AddMinutes(2))
            ],
            ConflictReceipts =
            [
                new WorkspaceRestoreConflictReceipt(
                    ReceiptId: "restore-conflict:missing-artifact",
                    Severity: "warning",
                    Kind: "restore_artifact_missing",
                    SubjectId: "install-01",
                    Summary: "Restore snapshot has no reconnectable artifact receipt.",
                    Resolution: "Refresh install linking before continuing.",
                    ObservedAtUtc: baselineObservedAtUtc),
                new WorkspaceRestoreConflictReceipt(
                    ReceiptId: null!,
                    Severity: "blocking",
                    Kind: null!,
                    SubjectId: " ",
                    Summary: "Entitlement restore conflict is recoverable even without a source receipt id.",
                    Resolution: "Open account access before continuing.",
                    ObservedAtUtc: baselineObservedAtUtc.AddMinutes(1),
                    Surface: "entitlement_sync",
                    BlocksContinue: true),
                new WorkspaceRestoreConflictReceipt(
                    ReceiptId: "restore-conflict:rotating-source-id:old",
                    Severity: "blocking",
                    Kind: "entitlement_replication_stale_claim",
                    SubjectId: "grant-rotating",
                    Summary: "Rotating source ids should still preserve first conflict observation by semantic receipt identity.",
                    Resolution: "Refresh entitlement replication before continuing.",
                    ObservedAtUtc: baselineObservedAtUtc.AddMinutes(2),
                    Surface: "entitlement_sync",
                    BlocksContinue: true)
            ]
        };

        WorkspaceRestoreProjection candidate = existing with
        {
            GeneratedAtUtc = DateTimeOffset.UtcNow,
            ProvenanceReceipts =
            [
                existing.ProvenanceReceipts![0] with { ObservedAtUtc = DateTimeOffset.UtcNow },
                existing.ProvenanceReceipts![1] with { ObservedAtUtc = DateTimeOffset.UtcNow },
                existing.ProvenanceReceipts![2] with { ObservedAtUtc = DateTimeOffset.UtcNow }
            ],
            ConflictReceipts =
            [
                existing.ConflictReceipts![0] with { ObservedAtUtc = DateTimeOffset.UtcNow },
                existing.ConflictReceipts![1] with { ObservedAtUtc = DateTimeOffset.UtcNow },
                existing.ConflictReceipts![2] with { ObservedAtUtc = DateTimeOffset.UtcNow }
            ]
        };

        WorkspaceRestoreProjection finalized = lifecycle.FinalizeRestoreProjection(existing, candidate, DateTimeOffset.UtcNow);

        VerificationAssert.Equal(
            existing.GeneratedAtUtc.ToString("O"),
            finalized.GeneratedAtUtc.ToString("O"),
            "Unchanged restore projections should keep the original generated timestamp.");
        VerificationAssert.Equal(
            existing.ProvenanceReceipts![0].ObservedAtUtc.ToString("O"),
            finalized.ProvenanceReceipts![0].ObservedAtUtc.ToString("O"),
            "Unchanged restore projections should preserve provenance receipt observation timestamps.");
        VerificationAssert.Equal(
            existing.ConflictReceipts![0].ObservedAtUtc.ToString("O"),
            finalized.ConflictReceipts![0].ObservedAtUtc.ToString("O"),
            "Unchanged restore projections should preserve conflict receipt observation timestamps.");
        VerificationAssert.Equal(
            existing.ProvenanceReceipts![1].ObservedAtUtc.ToString("O"),
            finalized.ProvenanceReceipts![1].ObservedAtUtc.ToString("O"),
            "Unchanged restore projections should preserve blank-id provenance receipt observation timestamps by recovered semantic identity.");
        VerificationAssert.Equal(
            existing.ConflictReceipts![1].ObservedAtUtc.ToString("O"),
            finalized.ConflictReceipts![1].ObservedAtUtc.ToString("O"),
            "Unchanged restore projections should preserve blank-id conflict receipt observation timestamps by recovered semantic identity.");

        DateTimeOffset rotatedFinalizeAtUtc = DateTimeOffset.UtcNow.AddMinutes(3);
        WorkspaceRestoreProjection rotatedCandidate = existing with
        {
            GeneratedAtUtc = DateTimeOffset.UtcNow,
            ProvenanceReceipts =
            [
                existing.ProvenanceReceipts![0],
                existing.ProvenanceReceipts![1],
                existing.ProvenanceReceipts![2] with
                {
                    ReceiptId = "restore-provenance:rotating-source-id:new",
                    ObservedAtUtc = DateTimeOffset.UtcNow
                }
            ],
            ConflictReceipts =
            [
                existing.ConflictReceipts![0],
                existing.ConflictReceipts![1],
                existing.ConflictReceipts![2] with
                {
                    ReceiptId = "restore-conflict:rotating-source-id:new",
                    ObservedAtUtc = DateTimeOffset.UtcNow
                }
            ]
        };

        WorkspaceRestoreProjection rotatedFinalized = lifecycle.FinalizeRestoreProjection(existing, rotatedCandidate, rotatedFinalizeAtUtc);

        VerificationAssert.Equal(
            rotatedFinalizeAtUtc.ToString("O"),
            rotatedFinalized.GeneratedAtUtc.ToString("O"),
            "Restore projections should advance the generated timestamp when source receipt ids rotate.");
        VerificationAssert.Equal(
            existing.ProvenanceReceipts![2].ObservedAtUtc.ToString("O"),
            rotatedFinalized.ProvenanceReceipts![2].ObservedAtUtc.ToString("O"),
            "Restore projections should preserve provenance receipt observation timestamps when source receipt ids rotate but semantic identity is stable.");
        VerificationAssert.Equal(
            existing.ConflictReceipts![2].ObservedAtUtc.ToString("O"),
            rotatedFinalized.ConflictReceipts![2].ObservedAtUtc.ToString("O"),
            "Restore projections should preserve conflict receipt observation timestamps when source receipt ids rotate but semantic identity is stable.");
    }

    private static void VerifyDuplicateSemanticReceiptsPreserveEarliestObservationTimestamps()
    {
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_WORKSPACE_RESTORE_RETENTION_DAYS"] = "30"
            })
            .Build();

        WorkspaceLifecyclePolicyService lifecycle = new(configuration);
        DateTimeOffset generatedAtUtc = DateTimeOffset.UtcNow.AddHours(-6);
        DateTimeOffset earliestObservedAtUtc = generatedAtUtc.AddMinutes(2);
        DateTimeOffset laterObservedAtUtc = generatedAtUtc.AddMinutes(9);

        WorkspaceRestoreProjection existing = BuildRestoreProjection("usr_duplicate_receipts", generatedAtUtc) with
        {
            ProvenanceReceipts =
            [
                new WorkspaceRestoreProvenanceReceipt(
                    ReceiptId: "restore-provenance:duplicate:newer",
                    Kind: "entitlement_replication_stale_claim",
                    SubjectId: "grant-duplicate",
                    Surface: "entitlement_sync",
                    Summary: "Later duplicate entitlement provenance receipt.",
                    Proof: "grant-duplicate",
                    ObservedAtUtc: laterObservedAtUtc),
                new WorkspaceRestoreProvenanceReceipt(
                    ReceiptId: "restore-provenance:duplicate:earlier",
                    Kind: "entitlement_replication_stale_claim",
                    SubjectId: "grant-duplicate",
                    Surface: "entitlement_sync",
                    Summary: "Earlier duplicate entitlement provenance receipt.",
                    Proof: "grant-duplicate",
                    ObservedAtUtc: earliestObservedAtUtc)
            ],
            ConflictReceipts =
            [
                new WorkspaceRestoreConflictReceipt(
                    ReceiptId: "restore-conflict:duplicate:newer",
                    Severity: "blocking",
                    Kind: "entitlement_replication_duplicate_grant",
                    SubjectId: "grant-duplicate",
                    Summary: "Later duplicate entitlement conflict receipt.",
                    Resolution: "Refresh entitlement replication before continuing.",
                    ObservedAtUtc: laterObservedAtUtc,
                    Surface: "entitlement_sync",
                    BlocksContinue: true),
                new WorkspaceRestoreConflictReceipt(
                    ReceiptId: "restore-conflict:duplicate:earlier",
                    Severity: "blocking",
                    Kind: "entitlement_replication_duplicate_grant",
                    SubjectId: "grant-duplicate",
                    Summary: "Earlier duplicate entitlement conflict receipt.",
                    Resolution: "Refresh entitlement replication before continuing.",
                    ObservedAtUtc: earliestObservedAtUtc,
                    Surface: "entitlement_sync",
                    BlocksContinue: true)
            ]
        };

        WorkspaceRestoreProjection candidate = existing with
        {
            GeneratedAtUtc = DateTimeOffset.UtcNow,
            ProvenanceReceipts =
            [
                existing.ProvenanceReceipts![0] with
                {
                    ReceiptId = "restore-provenance:duplicate:current",
                    ObservedAtUtc = DateTimeOffset.UtcNow
                }
            ],
            ConflictReceipts =
            [
                existing.ConflictReceipts![0] with
                {
                    ReceiptId = "restore-conflict:duplicate:current",
                    ObservedAtUtc = DateTimeOffset.UtcNow
                }
            ]
        };

        WorkspaceRestoreProjection finalized = lifecycle.FinalizeRestoreProjection(existing, candidate, DateTimeOffset.UtcNow);

        VerificationAssert.Equal(
            earliestObservedAtUtc.ToString("O"),
            finalized.ProvenanceReceipts![0].ObservedAtUtc.ToString("O"),
            "Duplicate semantic provenance receipts should preserve the earliest known observation timestamp instead of depending on existing list order.");
        VerificationAssert.Equal(
            earliestObservedAtUtc.ToString("O"),
            finalized.ConflictReceipts![0].ObservedAtUtc.ToString("O"),
            "Duplicate semantic conflict receipts should preserve the earliest known observation timestamp instead of depending on existing list order.");
    }

    private static string ResolveRepoRoot()
    {
        string current = AppContext.BaseDirectory;
        while (!string.IsNullOrWhiteSpace(current))
        {
            if (File.Exists(Path.Combine(current, "WORKLIST.md")) && Directory.Exists(Path.Combine(current, "Chummer.Run.Api")))
            {
                return current;
            }

            string? parent = Directory.GetParent(current)?.FullName;
            if (string.Equals(parent, current, StringComparison.Ordinal))
            {
                break;
            }

            current = parent ?? string.Empty;
        }

        throw new InvalidOperationException("Unable to resolve the chummer6-hub repo root for retention verification.");
    }
}
