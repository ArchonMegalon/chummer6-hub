using System.Reflection;
using Chummer.Campaign.Contracts;
using Chummer.Run.Api.Services.Community;
using Xunit;

namespace Chummer.Tests;

public sealed class CampaignSpineMigrationReceiptTests
{
    [Fact]
    public void Migration_receipts_emit_shared_envelopes()
    {
        RuleEnvironmentRef environment = new(
            EnvironmentId: "env-1",
            OwnerScope: "campaign",
            CompatibilityFingerprint: "sr5-mainline",
            ApprovalState: "approved",
            SourcePacks: ["sr5-core"],
            HouseRulePacks: [],
            OptionToggles: []);
        DateTimeOffset now = DateTimeOffset.Parse("2026-06-16T00:00:00Z");

        RunnerDossierProjection dossier = new(
            DossierId: "dossier-1",
            RunnerHandle: "ghostline",
            DisplayName: "Ghostline",
            Status: "active",
            OwnerUserId: "user-1",
            CrewId: null,
            CampaignId: "campaign-1",
            CurrentRunId: null,
            CurrentSceneId: null,
            RuleEnvironment: environment,
            LatestContinuity: null,
            BuildReceiptIds: [],
            SnapshotIds: [],
            Projections: [],
            CreatedAtUtc: now,
            UpdatedAtUtc: now);

        CampaignProjection campaign = new(
            CampaignId: "campaign-1",
            GroupId: "group-1",
            Name: "Neon Cradle",
            Status: "active",
            Visibility: "group",
            Summary: "Campaign continuity remains attached to one governed lane.",
            RuleEnvironment: environment,
            ActiveRunId: null,
            CrewIds: [],
            DossierIds: [],
            RunIds: [],
            LatestContinuity: null,
            CreatedAtUtc: now,
            UpdatedAtUtc: now);

        MethodInfo method = typeof(CampaignSpineService)
            .GetMethod("BuildMigrationReceipts", BindingFlags.NonPublic | BindingFlags.Static)
            ?? throw new InvalidOperationException("BuildMigrationReceipts was not found.");

        IReadOnlyList<LegacyMigrationReceiptProjection> receipts =
            Assert.IsAssignableFrom<IReadOnlyList<LegacyMigrationReceiptProjection>>(method.Invoke(
                null,
                [new[] { dossier }, new[] { campaign }]));

        LegacyMigrationReceiptProjection receipt = Assert.Single(receipts);
        Assert.NotNull(receipt.Envelope);
        Assert.Equal("legacy_migration", receipt.Envelope!.ReceiptKind);
        Assert.Equal("community.campaign_spine", receipt.Envelope.OwnerScope);
        Assert.Equal("dossier-1", receipt.Envelope.EvidenceRef);
    }
}
