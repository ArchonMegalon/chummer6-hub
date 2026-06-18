using Chummer.Campaign.Contracts;
using Chummer.Contracts.Receipts;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Contracts.Community;
using Microsoft.Extensions.Configuration;
using Xunit;

namespace Chummer.Tests;

public sealed class WorkspaceLifecyclePolicyServiceTests
{
    [Fact]
    public void FinalizeRestoreProjectionPreservesReceiptObservationTimestampsWhenContentIsUnchanged()
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
        ReceiptEnvelope existingEnvelope = new(
            ReceiptKind: "workspace_restore_provenance",
            OwnerScope: "community.workspace_restore",
            ProvenanceClass: ReceiptProvenanceClasses.Runtime,
            ExposureClass: ReceiptExposureClasses.SignedIn,
            LifecycleState: ReceiptLifecycleStates.Verified,
            CapturedAtUtc: baselineObservedAtUtc.AddSeconds(1),
            EvidenceRef: "install-01",
            ReviewState: "claimed_installation");
        ReceiptEnvelope candidateEnvelope = existingEnvelope with
        {
            CapturedAtUtc = DateTimeOffset.UtcNow,
            ReviewState = "claimed_installation_candidate"
        };

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
                    ObservedAtUtc: baselineObservedAtUtc,
                    Envelope: existingEnvelope)
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
                    ObservedAtUtc: baselineObservedAtUtc)
            ]
        };

        WorkspaceRestoreProjection candidate = existing with
        {
            GeneratedAtUtc = DateTimeOffset.UtcNow,
            ProvenanceReceipts =
            [
                existing.ProvenanceReceipts![0] with
                {
                    ObservedAtUtc = DateTimeOffset.UtcNow,
                    Envelope = candidateEnvelope
                }
            ],
            ConflictReceipts =
            [
                existing.ConflictReceipts![0] with { ObservedAtUtc = DateTimeOffset.UtcNow }
            ]
        };

        WorkspaceRestoreProjection finalized = lifecycle.FinalizeRestoreProjection(existing, candidate, DateTimeOffset.UtcNow);

        Assert.Equal(existing.GeneratedAtUtc.ToString("O"), finalized.GeneratedAtUtc.ToString("O"));
        Assert.Equal(existing.ProvenanceReceipts![0].ObservedAtUtc.ToString("O"), finalized.ProvenanceReceipts![0].ObservedAtUtc.ToString("O"));
        Assert.Equal(existingEnvelope, finalized.ProvenanceReceipts![0].Envelope);
        Assert.Equal(existing.ConflictReceipts![0].ObservedAtUtc.ToString("O"), finalized.ConflictReceipts![0].ObservedAtUtc.ToString("O"));
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
}
