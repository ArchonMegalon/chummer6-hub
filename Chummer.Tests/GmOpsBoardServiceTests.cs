using Chummer.Play.Contracts.Relay;
using Chummer.Run.AI.Services.Ops;
using Chummer.Run.AI.Services.Session;
using Chummer.Run.AI.Services.Spider;
using Chummer.Run.Contracts.Ops;
using Xunit;

namespace Chummer.Tests;

public sealed class GmOpsBoardServiceTests
{
    [Fact]
    public void ReconcilePortableAssets_DropsGovernedProject_WhenRequiredFieldsAreMissing()
    {
        var service = CreateService();
        var now = DateTimeOffset.UtcNow;
        var asset = new OfflineSyncPrepAsset(
            AssetId: "prep_missing_fields",
            CampaignId: "campaign_ops",
            SessionId: "session_ops",
            SceneId: "scene_ops",
            Title: "Governed packet with sparse provenance",
            Kind: nameof(GmPrepAssetKind.Note),
            Audience: nameof(GmPrepAssetAudience.GameMaster),
            Summary: "Should not keep malformed governed project payload",
            Body: "ops",
            Tags: ["governed-packet"],
            ChecklistItems: Array.Empty<OfflineSyncPrepChecklistItem>(),
            Status: "draft",
            CreatedBy: "gm.ops",
            RuntimeFingerprint: "ops-fingerprint",
            CreatedAtUtc: now.AddMinutes(-5),
            UpdatedAtUtc: now,
            GovernedProject: new OfflineSyncPrepGovernedProjectReference(
                ProjectKind: "npc-pack",
                ProjectId: "renraku-security",
                Title: null!,
                RulesetId: "sr5",
                LinkTarget: " ",
                TrustTier: "verified"));

        OfflineSyncSurfaceMergeResult result = service.ReconcilePortableAssets([asset]);
        GmPrepAssetRecord? stored = service.GetPrepAsset(asset.AssetId);
        Assert.NotNull(stored);

        Assert.Equal(1, result.ImportedCount);
        Assert.Null(stored!.GovernedProject);
    }

    [Fact]
    public void ReconcilePortableAssets_NormalizesGovernedProject_WhenFieldsAreComplete()
    {
        var service = CreateService();
        var now = DateTimeOffset.UtcNow;
        var asset = new OfflineSyncPrepAsset(
            AssetId: "prep_complete_fields",
            CampaignId: "campaign_ops",
            SessionId: "session_ops",
            SceneId: "scene_ops",
            Title: "Governed packet with complete provenance",
            Kind: nameof(GmPrepAssetKind.Note),
            Audience: nameof(GmPrepAssetAudience.GameMaster),
            Summary: "Should keep normalized governed project payload",
            Body: "ops",
            Tags: ["governed-packet"],
            ChecklistItems: Array.Empty<OfflineSyncPrepChecklistItem>(),
            Status: "draft",
            CreatedBy: "gm.ops",
            RuntimeFingerprint: "ops-fingerprint",
            CreatedAtUtc: now.AddMinutes(-5),
            UpdatedAtUtc: now,
            GovernedProject: new OfflineSyncPrepGovernedProjectReference(
                ProjectKind: " npc-pack ",
                ProjectId: " renraku-security ",
                Title: " Renraku security roster ",
                RulesetId: " sr5 ",
                LinkTarget: " /hub/npc-packs/renraku-security ",
                TrustTier: " verified ",
                RuntimeFingerprint: " runtime:1 "));

        service.ReconcilePortableAssets([asset]);
        GmPrepAssetRecord? stored = service.GetPrepAsset(asset.AssetId);
        Assert.NotNull(stored);

        GmPrepAssetGovernedProjectReference? governed = stored!.GovernedProject;
        Assert.NotNull(governed);
        Assert.Equal("npc-pack", governed!.ProjectKind);
        Assert.Equal("renraku-security", governed.ProjectId);
        Assert.Equal("Renraku security roster", governed.Title);
        Assert.Equal("sr5", governed.RulesetId);
        Assert.Equal("/hub/npc-packs/renraku-security", governed.LinkTarget);
        Assert.Equal("verified", governed.TrustTier);
        Assert.Equal("runtime:1", governed.RuntimeFingerprint);
    }

    private static GmOpsBoardService CreateService()
    {
        var ledger = new SessionLedgerService();
        var outbox = new DeliveryOutboxService();
        return new GmOpsBoardService(ledger, outbox);
    }
}
