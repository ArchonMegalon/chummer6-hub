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
    public void ReconcilePortableAssets_SkipsAssets_WhenRequiredAssetFieldsAreMissing()
    {
        var service = CreateService();
        var now = DateTimeOffset.UtcNow;
        var missingCampaign = BuildPortableAsset(
            assetId: "prep_missing_campaign",
            now: now,
            campaignId: " ");
        var missingTitle = BuildPortableAsset(
            assetId: "prep_missing_title",
            now: now.AddMinutes(1),
            title: "");
        var missingBody = BuildPortableAsset(
            assetId: "prep_missing_body",
            now: now.AddMinutes(2),
            body: "   ");

        OfflineSyncSurfaceMergeResult result = service.ReconcilePortableAssets([missingCampaign, missingTitle, missingBody]);

        Assert.Equal(0, result.ImportedCount);
        Assert.Equal(3, result.SkippedCount);
        Assert.Equal(3, result.Conflicts.Count);
        Assert.All(result.Conflicts, conflict =>
        {
            Assert.Equal("ops-prep", conflict.Surface);
            Assert.Equal("invalid-asset-required-fields", conflict.Reason);
            Assert.Equal("skipped-invalid", conflict.Resolution);
        });
        Assert.Null(service.GetPrepAsset("prep_missing_campaign"));
        Assert.Null(service.GetPrepAsset("prep_missing_title"));
        Assert.Null(service.GetPrepAsset("prep_missing_body"));
    }

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

    [Fact]
    public void ReconcilePortableAssets_UpdatesExistingAsset_WhenRemoteAssetIdHasWhitespace()
    {
        var service = CreateService();
        var now = DateTimeOffset.UtcNow;
        var initial = BuildPortableAsset(
            assetId: "prep_whitespace_id",
            now: now,
            title: "Initial packet");
        var updated = BuildPortableAsset(
            assetId: " prep_whitespace_id ",
            now: now.AddMinutes(2),
            title: "Updated packet");

        OfflineSyncSurfaceMergeResult result = service.ReconcilePortableAssets([initial, updated]);

        Assert.Equal(2, result.ImportedCount);
        Assert.Equal(0, result.SkippedCount);
        GmPrepAssetRecord? stored = service.GetPrepAsset("prep_whitespace_id");
        Assert.NotNull(stored);
        Assert.Equal("Updated packet", stored!.Title);

        GmPrepAssetListResponse listed = service.ListPrepAssets(campaignId: "campaign_ops");
        Assert.Single(listed.Items);
        Assert.Equal("prep_whitespace_id", listed.Items[0].AssetId);
    }

    private static GmOpsBoardService CreateService()
    {
        var ledger = new SessionLedgerService();
        var outbox = new DeliveryOutboxService();
        return new GmOpsBoardService(ledger, outbox);
    }

    private static OfflineSyncPrepAsset BuildPortableAsset(
        string assetId,
        DateTimeOffset now,
        string campaignId = "campaign_ops",
        string title = "Portable prep asset",
        string body = "portable body") =>
        new(
            AssetId: assetId,
            CampaignId: campaignId,
            SessionId: "session_ops",
            SceneId: "scene_ops",
            Title: title,
            Kind: nameof(GmPrepAssetKind.Note),
            Audience: nameof(GmPrepAssetAudience.GameMaster),
            Summary: "portable",
            Body: body,
            Tags: ["portable"],
            ChecklistItems: Array.Empty<OfflineSyncPrepChecklistItem>(),
            Status: "draft",
            CreatedBy: "gm.ops",
            RuntimeFingerprint: "ops-fingerprint",
            CreatedAtUtc: now.AddMinutes(-5),
            UpdatedAtUtc: now);
}
