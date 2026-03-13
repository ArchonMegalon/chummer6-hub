using Chummer.Media.Contracts;
using Chummer.Hub.Registry.Contracts;
using Chummer.Run.AI.Services.Assets;
using Chummer.Run.AI.Services.Gateway;
using Chummer.Run.AI.Services.Session;
using PlayGateway = Chummer.Play.Contracts.Gateway;
using Chummer.Run.Registry.Services;
using Microsoft.Extensions.Configuration;
using System.Threading;

namespace RunServicesVerification;

internal static class PipelineProjectionVerification
{
    public static async Task RunAsync()
    {
        await VerifyRelayProjectionAsync();
        await VerifyApprovalAndMediaProjectionAsync();
        await VerifyGatewayProjectionAsync();
        VerifyRegistryProjection();
    }

    private static async Task VerifyRelayProjectionAsync()
    {
        var ledger = new SessionLedgerService();
        await ledger.MergeEventsAsync(
        [
            new SessionEventEnvelope("session-c10", "scene-a", "event", "{}", DateTimeOffset.UtcNow, "evt-1", IdempotencyKey: "id-1"),
            new SessionEventEnvelope("session-c10", "scene-a", "event", "{}", DateTimeOffset.UtcNow, "evt-1", IdempotencyKey: "id-1"),
            new SessionEventEnvelope("session-c10", "scene-b", "wrong-scene", "{}", DateTimeOffset.UtcNow, "evt-2", IdempotencyKey: "id-2")
        ]);

        var projection = ledger.GetRelayPipelineProjection();
        VerificationAssert.Equal("relay", projection.Pipeline, "Relay pipeline projection should identify relay.");
        VerificationAssert.True(projection.Observability.ProcessedCount >= 3, "Relay projection should include processed count.");
        VerificationAssert.True(projection.Idempotency.ReplayCount >= 1, "Relay projection should report idempotency replay.");
        VerificationAssert.True(projection.DeadLetter.Count >= 1, "Relay projection should report dead-letter entries for ignored events.");
    }

    private static async Task VerifyApprovalAndMediaProjectionAsync()
    {
        var assets = new AssetLifecycleService();
        var jobs = new MediaRenderJobService(assets);

        var asset = await assets.StoreAsync(
            category: "approval/c10",
            content: "{\"payload\":true}",
            source: "verification",
            policy: new AssetLifecyclePolicy(
                CacheTtl: TimeSpan.FromMinutes(5),
                LongTermCache: false,
                MaxBytes: 2048,
                RequiresApproval: true,
                PersistOnApproval: true,
                StorageClass: AssetStorageClass.ObjectStorage,
                AllowPersistentPinning: true));

        var blocked = false;
        try
        {
            await assets.ApplyLifecycleAsync(asset.AssetId, new AssetLifecycleMutationRequest(Persist: true, Reason: "blocked"));
        }
        catch (InvalidOperationException)
        {
            blocked = true;
        }

        VerificationAssert.True(blocked, "Approval projection setup should produce a dead-letter lifecycle mutation.");

        await jobs.EnqueueAsync(new MediaRenderJobEnqueueRequest(
            JobType: MediaRenderJobType.DocumentPreviewImage,
            DeduplicationKey: "media-c10",
            Category: "preview",
            Payload: "<html/>",
            Source: "verification",
            CacheTtl: TimeSpan.FromMinutes(1),
            MaxBytes: 256,
            RequiresApproval: false,
            PersistOnApproval: false,
            AllowPersistentPinning: false));
        await jobs.EnqueueAsync(new MediaRenderJobEnqueueRequest(
            JobType: MediaRenderJobType.DocumentPreviewImage,
            DeduplicationKey: "media-c10",
            Category: "preview",
            Payload: "<html/>",
            Source: "verification",
            CacheTtl: TimeSpan.FromMinutes(1),
            MaxBytes: 256,
            RequiresApproval: false,
            PersistOnApproval: false,
            AllowPersistentPinning: false));

        var approvalProjection = assets.GetApprovalPipelineProjection();
        var mediaProjection = jobs.GetMediaPipelineProjection();
        VerificationAssert.Equal("approval", approvalProjection.Pipeline, "Approval projection should identify the approval pipeline.");
        VerificationAssert.True(approvalProjection.DeadLetter.Count >= 1, "Approval projection should include dead-letter lifecycle blocks.");
        VerificationAssert.Equal("media", mediaProjection.Pipeline, "Media projection should identify media pipeline.");
        VerificationAssert.True(mediaProjection.Idempotency.ReplayCount >= 1, "Media projection should include dedupe replay count.");
    }

    private static async Task VerifyGatewayProjectionAsync()
    {
        var config = new ConfigurationBuilder().AddInMemoryCollection(new Dictionary<string, string?>
        {
            ["AiGateway:Providers:AiMagicx:Enabled"] = "true",
            ["AiGateway:Providers:OneMinAi:Enabled"] = "true",
            ["AiGateway:MonthlyAllowance"] = "500",
            ["AiGateway:BurstAllowancePerMinute"] = "200"
        }).Build();

        var router = new ProviderRouter(config);
        var budget = new AiBudgetService(config);
        var promptRegistry = new PromptRegistry();
        var providers = new IProviderAdapter[]
        {
            new MockProviderAdapter(PlayGateway.AiProvider.AiMagicx, enabled: true, primaryForStructuredOutput: true),
            new MockProviderAdapter(PlayGateway.AiProvider.OneMinAi, enabled: true, primaryForStructuredOutput: false)
        };
        var gateway = new AiGatewayService(router, providers, budget, promptRegistry);

        var request = new PlayGateway.ProviderRouteRequest(
            Purpose: "projection",
            Prompt: "hello projection",
            StructuredOutput: false,
            MaxTokens: 1200,
            SessionId: "session-c10");
        await gateway.ExecuteRouteAsync(request, CancellationToken.None);
        await gateway.ExecuteRouteAsync(request, CancellationToken.None);

        var status = await gateway.GetStatusAsync();
        VerificationAssert.True(status.SelectionVisibility.TotalRoutes >= 2, "Gateway status should publish provider-selection totals.");
        VerificationAssert.True(status.SelectionVisibility.RecentAudits.Count >= 2, "Gateway status should publish route audit entries.");

        var projection = gateway.GetGatewayPipelineProjection();
        VerificationAssert.Equal("ai-gateway", projection.Pipeline, "Gateway projection should identify ai-gateway.");
        VerificationAssert.True(projection.Idempotency.ReplayCount >= 1, "Gateway projection should track replayed requests.");
        VerificationAssert.True(projection.Cost.EstimatedUsd > 0, "Gateway projection should accumulate estimated cost.");
    }

    private static void VerifyRegistryProjection()
    {
        var store = new HubArtifactStore();
        var artifact = store.UpsertArtifact(new HubArtifactCreateRequest(
            Name: "Registry C10",
            Kind: HubArtifactKind.RulePack,
            Version: "1.0.0",
            RulesetId: "sr6",
            Visibility: ArtifactVisibilityModes.LocalOnly,
            TrustTier: ArtifactTrustTiers.LocalOnly,
            OwnerId: "ops",
            PublisherId: null,
            Summary: "observability projection",
            Description: null,
            RuntimeFingerprint: "fp",
            StateReason: null));
        _ = store.IssueRuntimeBundle(new RuntimeBundleIssueRequest(
            SessionId: "session-c10",
            SceneId: "scene-c10",
            Head: RuntimeBundleHeadKind.Session,
            SourceBundleVersion: "bundle-1",
            ProjectionFingerprint: "abcd1234",
            ProjectionVersion: 1,
            Ready: true,
            OfflineCapable: true,
            CollaborationMode: "hybrid",
            InvalidationSignals: ["projection:1"],
            IncludedEventTypes: ["event"],
            SupportedExchangeFormats: ["foundry-vtt.scene-ledger.v1"],
            OwnerId: "ops"));
        _ = store.IssueRuntimeBundle(new RuntimeBundleIssueRequest(
            SessionId: "session-c10",
            SceneId: "scene-c10",
            Head: RuntimeBundleHeadKind.Session,
            SourceBundleVersion: "bundle-1",
            ProjectionFingerprint: "abcd1234",
            ProjectionVersion: 1,
            Ready: true,
            OfflineCapable: true,
            CollaborationMode: "hybrid",
            InvalidationSignals: ["projection:1"],
            IncludedEventTypes: ["event"],
            SupportedExchangeFormats: ["foundry-vtt.scene-ledger.v1"],
            OwnerId: "ops"));

        _ = store.AttemptDelete(artifact.Id);
        var projection = store.GetRegistryPipelineProjection();
        VerificationAssert.Equal("registry", projection.Pipeline, "Registry projection should identify registry pipeline.");
        VerificationAssert.True(projection.Idempotency.ReplayCount >= 1, "Registry projection should track idempotent runtime issue repeats.");
        VerificationAssert.True(projection.DeadLetter.Count >= 1, "Registry projection should include dead-letter delete attempts.");
    }
}
