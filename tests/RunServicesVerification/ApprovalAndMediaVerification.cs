using Chummer.Media.Contracts;
using Chummer.Run.AI.Services.Assets;
using Chummer.Run.AI.Services.Creative;
using Chummer.Run.AI.Services.Session;
using Chummer.Run.AI.Services.Spider;
using Chummer.Run.Contracts.Media;

namespace RunServicesVerification;

internal static class ApprovalAndMediaVerification
{
    public static async Task RunAsync()
    {
        var assets = new AssetLifecycleService();
        var mediaJobs = new MediaRenderJobService(assets);

        await VerifyAssetApprovalLifecycleAsync(assets);
        await VerifyMediaJobReuseAndExpiryAsync(mediaJobs);
        await VerifyPortraitApprovalFlowAsync(assets, mediaJobs);
        await VerifyPacketAttachmentFlowAsync(mediaJobs);
        await VerifyNewsApprovalGateAsync(assets, mediaJobs);
    }

    private static async Task VerifyAssetApprovalLifecycleAsync(IAssetLifecycleService assets)
    {
        var stored = await assets.StoreAsync(
            category: "approval/fixture",
            content: "{\"asset\":\"draft\"}",
            source: "verification",
            policy: new AssetLifecyclePolicy(
                CacheTtl: TimeSpan.FromMinutes(5),
                LongTermCache: false,
                MaxBytes: 2048,
                RequiresApproval: true,
                PersistOnApproval: true,
                StorageClass: AssetStorageClass.ObjectStorage,
                AllowPersistentPinning: true));

        VerificationAssert.Equal(AssetApprovalState.Pending, stored.ApprovalState, "Approval-gated assets should begin pending approval.");
        VerificationAssert.Equal(AssetRetentionState.ApprovalPending, stored.RetentionState, "Approval-gated assets should begin pending.");

        var persistBlocked = false;
        try
        {
            await assets.ApplyLifecycleAsync(
                stored.AssetId,
                new AssetLifecycleMutationRequest(Persist: true, Reason: "should fail"));
        }
        catch (InvalidOperationException)
        {
            persistBlocked = true;
        }

        VerificationAssert.True(persistBlocked, "Assets should not persist before approval.");

        var approved = await assets.ApplyLifecycleAsync(
            stored.AssetId,
            new AssetLifecycleMutationRequest(
                ApprovalState: AssetApprovalState.Approved,
                Pin: true,
                Persist: true,
                Reason: "approved for use"));
        VerificationAssert.NotNull(approved, "Approved asset should still exist.");
        VerificationAssert.Equal(AssetRetentionState.Pinned, approved!.RetentionState, "Approved + pinned assets should be pinned.");

        var rejected = await assets.ApplyLifecycleAsync(
            stored.AssetId,
            new AssetLifecycleMutationRequest(
                ApprovalState: AssetApprovalState.Rejected,
                Pin: false,
                Persist: false,
                Reason: "superseded"));
        VerificationAssert.NotNull(rejected, "Rejected asset should still resolve for lifecycle inspection.");
        VerificationAssert.Equal(AssetRetentionState.Rejected, rejected!.RetentionState, "Rejected assets should enter rejected retention.");
    }

    private static async Task VerifyMediaJobReuseAndExpiryAsync(IMediaRenderJobService mediaJobs)
    {
        var first = await mediaJobs.EnqueueAsync(new MediaRenderJobEnqueueRequest(
            JobType: MediaRenderJobType.DocumentPreviewImage,
            DeduplicationKey: "job:dedupe",
            Category: "packet/preview",
            Payload: "<html>preview</html>",
            Source: "verification",
            CacheTtl: TimeSpan.FromMilliseconds(40),
            MaxBytes: 4096,
            RequiresApproval: true,
            PersistOnApproval: true,
            AllowPersistentPinning: true));

        var ready = await WaitForJobAsync(mediaJobs, first.JobId, MediaRenderJobState.Succeeded);
        VerificationAssert.NotNull(ready.AssetId, "Completed media jobs should carry an asset id.");

        var reused = await mediaJobs.EnqueueAsync(new MediaRenderJobEnqueueRequest(
            JobType: MediaRenderJobType.DocumentPreviewImage,
            DeduplicationKey: "job:dedupe",
            Category: "packet/preview",
            Payload: "<html>preview</html>",
            Source: "verification",
            CacheTtl: TimeSpan.FromMilliseconds(40),
            MaxBytes: 4096,
            RequiresApproval: true,
            PersistOnApproval: true,
            AllowPersistentPinning: true));
        VerificationAssert.Equal(first.JobId, reused.JobId, "Active job cache should reuse the existing job for the same dedupe key.");

        await Task.Delay(80);
        var expired = mediaJobs.Get(first.JobId);
        VerificationAssert.NotNull(expired, "Expired jobs should still be inspectable.");
        VerificationAssert.Equal(MediaRenderJobState.Expired, expired!.State, "Expired job TTL should move completed jobs to expired.");

        var renewed = await mediaJobs.EnqueueAsync(new MediaRenderJobEnqueueRequest(
            JobType: MediaRenderJobType.DocumentPreviewImage,
            DeduplicationKey: "job:dedupe",
            Category: "packet/preview",
            Payload: "<html>preview</html>",
            Source: "verification",
            CacheTtl: TimeSpan.FromMilliseconds(40),
            MaxBytes: 4096,
            RequiresApproval: true,
            PersistOnApproval: true,
            AllowPersistentPinning: true));
        VerificationAssert.True(!string.Equals(first.JobId, renewed.JobId, StringComparison.Ordinal), "Expired jobs should not be reused.");
    }

    private static async Task VerifyPortraitApprovalFlowAsync(IAssetLifecycleService assets, IMediaRenderJobService mediaJobs)
    {
        var portraits = new PortraitForgeService(assets, mediaJobs);
        var forged = await portraits.ForgeAsync(new PortraitForgeRequest(
            EntityId: "npc:glitch",
            Style: "gritty-polaroid",
            Notes: "first pass",
            AllowUnderscover: true));

        var canonical = forged.Variants.First(static variant => string.Equals(variant.Variant, "canonical", StringComparison.OrdinalIgnoreCase));
        await WaitForJobAsync(mediaJobs, canonical.JobId, MediaRenderJobState.Succeeded);

        var approved = await portraits.ApproveAsync(
            forged.PortraitDraftId,
            new PortraitApprovalRequest(
                Variant: "canonical",
                ApprovedBy: "gm.ops",
                Notes: "lock the canon portrait",
                PinCanonical: true));
        VerificationAssert.NotNull(approved, "Portrait approval should return the updated draft.");
        VerificationAssert.Equal("approved", approved!.DraftState, "Approved portrait drafts should enter the approved state.");
        VerificationAssert.True(approved.Variants.Any(static variant => variant.IsCanonical), "Approved portrait drafts should expose a canonical variant.");

        var approvedVariant = approved.Variants.Single(static variant => variant.IsCanonical);
        VerificationAssert.Equal(AssetApprovalState.Approved, approvedVariant.ApprovalState, "Canonical portrait asset should be approved.");
        VerificationAssert.Equal(AssetRetentionState.Pinned, approvedVariant.RetentionState, "Canonical portrait asset should be pinned when requested.");
    }

    private static async Task VerifyPacketAttachmentFlowAsync(IMediaRenderJobService mediaJobs)
    {
        var packets = new PacketFactoryService(mediaJobs);
        var created = await packets.CreateAsync(new PacketFactoryRequest(
            Title: "Johnson packet",
            Subject: "Ares extraction",
            References: ["matrix log", "security still"],
            Attachments:
            [
                new PacketAttachmentRequest(PacketAttachmentTargetKind.Route, "campaign-7", "Campaign"),
                new PacketAttachmentRequest(PacketAttachmentTargetKind.Route, "campaign-7", "Campaign duplicate")
            ]));

        VerificationAssert.Equal(3, created.Artifacts!.Count, "Packet factory should enqueue preview, PDF, and thumbnail artifacts.");
        VerificationAssert.Equal(1, created.Attachments!.Count, "Packet attachments should dedupe duplicate targets.");
    }

    private static async Task VerifyNewsApprovalGateAsync(IAssetLifecycleService assets, IMediaRenderJobService mediaJobs)
    {
        var ledger = new SessionLedgerService();
        await ledger.MergeEventsAsync(
        [
            new SessionEventEnvelope(
                SessionId: "session-77",
                SceneId: "scene-7",
                EventType: "alarm-tripped",
                Payload: "Knight Errant response incoming",
                AtUtc: DateTimeOffset.UtcNow.AddMinutes(-3),
                EventId: "evt-1",
                SceneRevision: "scene-7:r4",
                IdempotencyKey: "alarm:1")
        ]);

        var memory = new SessionMemoryService(ledger);
        var outbox = new DeliveryOutboxService();
        var news = new NewsNetworkService(mediaJobs, assets, ledger, memory, outbox);
        var brief = await news.BuildNewsBriefAsync(new NewsBriefRequest(
            CampaignId: "campaign-77",
            SessionId: "session-77",
            SceneId: "scene-7",
            SceneRevision: "scene-7:r4",
            ApprovedNotes: ["Knight Errant is inbound"],
            IncludeVideo: true));

        var blocked = await news.DeliverAsync(
            brief.NewsBriefId,
            new NewsBriefDeliveryRequest(
                SessionId: "session-77",
                SceneId: "scene-7",
                SceneRevision: "scene-7:r4",
                RequestedBy: "gm.ops",
                Channel: "gm-ops-board",
                Archive: false));
        VerificationAssert.Equal("approval-required", blocked.Outcome, "News briefs should not deliver before recap approval.");

        await assets.ApplyLifecycleAsync(
            brief.RecapAssetId,
            new AssetLifecycleMutationRequest(
                ApprovalState: AssetApprovalState.Approved,
                Pin: true,
                Persist: true,
                Reason: "approved for delivery"));

        var delivered = await news.DeliverAsync(
            brief.NewsBriefId,
            new NewsBriefDeliveryRequest(
                SessionId: "session-77",
                SceneId: "scene-7",
                SceneRevision: "scene-7:r4",
                RequestedBy: "gm.ops",
                Channel: "gm-ops-board",
                Archive: false));
        VerificationAssert.Equal("delivered", delivered.Outcome, "Approved news briefs should deliver.");
        VerificationAssert.Equal(1, delivered.Messages.Count, "Approved news briefs should enqueue one message for one channel.");
    }

    private static async Task<MediaRenderJobStatus> WaitForJobAsync(
        IMediaRenderJobService mediaJobs,
        string jobId,
        MediaRenderJobState terminalState)
    {
        for (var attempt = 0; attempt < 100; attempt++)
        {
            var job = mediaJobs.Get(jobId);
            if (job is not null && job.State == terminalState)
            {
                return job;
            }

            await Task.Delay(20);
        }

        throw new InvalidOperationException($"Timed out waiting for job '{jobId}' to reach state '{terminalState}'.");
    }
}
