using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Contracts.Community;
using Microsoft.Extensions.Configuration;
using Xunit;

namespace Chummer.Tests;

public sealed class OriginChapterSceneRequestBridgeTests : IDisposable
{
    private readonly string root = Path.Combine(Path.GetTempPath(), "origin-scene-tests-" + Guid.NewGuid().ToString("N"));
    private const string Prose = "Nach dem Regen liegen helle Steine zwischen den Wurzeln. Ein ruhiger Morgen.";
    private static string Sha(string value) => Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(value)));
    private OriginChapterAuthoringService Service() => new(new ConfigurationBuilder().AddInMemoryCollection(
        new Dictionary<string, string?> { ["CHUMMER_RUNTIME_STATE_ROOT"] = root }).Build());

    private OriginChapterAuthoringService Prepare(bool accepted = true)
    {
        var service = Service();
        var source = new OriginChapterSource("workspace", "chapter", new string('a', 64), "decision", "de-DE", "Synthetic",
            [new("fact", "decision", "An approved childhood scene.")]);
        var job = service.Create("owner-a", new("request", source, true), () => true);
        var work = Assert.Single(service.PendingForWorker(10));
        service.AdmitForWorker(work.WorkId, job.SourceDigest, "admission");
        service.CompleteForWorker(work.WorkId, job.SourceDigest, "admission", Prose, new string('b', 64));
        if (accepted)
            service.AcceptReading("owner-a", job.RequestId, job.SourceDigest, new string('b', 64), Sha(Prose), true, () => true);
        return service;
    }

    [Fact]
    public void Composes_private_offline_scene_from_exact_reader_accepted_text_without_quota_or_generation()
    {
        using var service = Prepare();
        var before = JsonSerializer.Serialize(service.Get("owner-a", "request"));
        var request = new OriginChapterSceneRequestBridge(service).Compose("owner-a", "request", Sha(Prose),
            Prose, "Steine nach dem Regen", true, () => true);
        var capability = new HorizonCapabilityService(new ConfigurationBuilder().Build()).GetCapability("origin-dossier", "origin-dossier-media");
        var result = new HorizonGovernedRenderRequestComposerService().Compose(capability, request.SourceRef, request.GovernedRenderRequest!);
        Assert.True(result.Accepted, string.Join(",", result.BlockedReasons));
        Assert.Equal("private", result.Contract!.Audience);
        Assert.Null(result.Contract.PreferredProvider);
        Assert.Equal("origin-owner:" + Sha("owner-a"), result.Contract.RequestedBy);
        string identity = Sha(string.Join('\0', Sha("owner-a"), "workspace", "chapter", new string('a', 64), Sha(Prose)));
        Assert.Equal(identity, result.Contract.WorkItemId);
        Assert.Equal(identity, new OriginChapterSceneRequestBridge(service).ResolveIdentity("owner-a", "request", Sha(Prose), () => true));
        var artifact = Assert.Single(result.Contract.Artifacts);
        Assert.Equal(identity, artifact.DeduplicationKey);
        Assert.True(artifact.RequiresApproval);
        Assert.True(artifact.PersistOnApproval);
        Assert.False(artifact.AllowPersistentPinning);
        Assert.Equal(4 * 1024 * 1024, artifact.MaxBytes);
        using var payload = JsonDocument.Parse(artifact.Payload);
        Assert.Equal(Sha(Prose), payload.RootElement.GetProperty("textDigest").GetString());
        Assert.Contains(Prose, payload.RootElement.GetProperty("prompt").GetString());
        Assert.Equal(before, JsonSerializer.Serialize(service.Get("owner-a", "request")));
    }

    [Fact]
    public void Scene_passes_real_artifact_admission_without_weakening_the_disabled_capability_gate()
    {
        using var service = Prepare();
        var request = new OriginChapterSceneRequestBridge(service).Compose("owner-a", "request", Sha(Prose),
            Prose, "Steine nach dem Regen", true, () => true);
        var admission = new HorizonArtifactRequestService(new(new ConfigurationBuilder().Build()));
        var disabled = admission.BuildRequest(request);
        Assert.Equal("blocked", disabled.Status);
        Assert.Equal("capability enabled", Assert.Single(disabled.BlockedReasons));
        // Compose-only audit: deliberately no quota or provider execution. This
        // still exercises all source/consent/private-visibility admission checks.
        var preview = admission.BuildRequest(request, requireEnabledCapability: false);
        Assert.Equal("accepted", preview.Status);
        Assert.Empty(preview.BlockedReasons);
        Assert.StartsWith("origin-dossier:scene:", preview.SourceRef);
        Assert.Equal(preview.SourceRef, preview.GovernedRenderRequest!.SourceRef);
        Assert.Null(preview.Quota);
    }

    [Fact]
    public void Draft_provider_text_is_not_reader_acceptance()
    {
        using var service = Prepare(false);
        Assert.Throws<InvalidOperationException>(() => new OriginChapterSceneRequestBridge(service).Compose(
            "owner-a", "request", Sha(Prose), Prose, "Scene", true, () => true));
        Assert.Throws<InvalidOperationException>(() => new OriginChapterSceneRequestBridge(service).ResolveIdentity(
            "owner-a", "request", Sha(Prose), () => true));
    }

    private IConfiguration AdmissionConfig(bool enabled = true) => new ConfigurationBuilder().AddInMemoryCollection(
        new Dictionary<string, string?>
        {
            ["CHUMMER_HORIZON_ARTIFACT_USAGE_STORAGE_PROVIDER"] = "teable",
            ["CHUMMER_HORIZON_REQUEST_RECEIPT_STORAGE_PROVIDER"] = "teable",
            ["CHUMMER_MYFIRSTBOOK_USAGE_STORAGE_PROVIDER"] = "teable",
            ["CHUMMER_BILLING_MEMBERSHIP_STORAGE_PROVIDER"] = "teable",
            ["HorizonCapabilities:origin-dossier:origin-dossier-media:Enabled"] = enabled.ToString(),
            ["HorizonCapabilities:origin-dossier:origin-dossier-media:FreeWeeklyLimit"] = "2"
        }).Build();

    private HorizonArtifactRequestService Admission(TeableRevisionStoreTests.Remote remote, bool enabled = true)
    {
        var config = AdmissionConfig(enabled);
        var billing = new BrilliantDirectoriesBillingService(new(config, primary: remote.Store()),
            new(config, primary: remote.Store()), config);
        return new(new(config), new(new(config, remote.Store()), new(config), billing), new(config, remote.Store()));
    }

    [Fact]
    public void Reconnect_and_cold_primary_restore_reuse_one_exact_charged_scene()
    {
        using var chapters = Prepare();
        using var remote = new TeableRevisionStoreTests.Remote();
        var request = new OriginChapterSceneRequestBridge(chapters).Compose("owner-a", "request", Sha(Prose),
            Prose, "Scene", true, () => true) with { UserId = "hub-user-a" };
        var first = Admission(remote).AdmitPrivateOriginScene(request);
        var restored = Admission(remote).AdmitPrivateOriginScene(request);
        Assert.Equal(JsonSerializer.Serialize(first), JsonSerializer.Serialize(restored));
        Assert.Equal("hub-user-a", first.RequestedByUserId);
        Assert.Equal("origin-owner:" + Sha("owner-a"), first.GovernedRenderRequest!.RequestedBy);
        Assert.Equal(1, first.Quota!.WindowUsed);
        Assert.Equal(1, remote.HeadPosts);
        // Even generic admission cannot charge this scene again in a new week.
        Assert.Throws<InvalidOperationException>(() => Admission(remote).BuildRequest(request,
            first.CreatedAtUtc.AddDays(7), consumeQuota: true));
        Assert.Equal(1, remote.HeadPosts);
    }

    [Fact]
    public void Concurrent_identical_scene_admission_returns_the_winning_primary_receipt()
    {
        using var chapters = Prepare();
        using var remote = new TeableRevisionStoreTests.Remote();
        var request = new OriginChapterSceneRequestBridge(chapters).Compose("owner-a", "request", Sha(Prose),
            Prose, "Scene", true, () => true) with { UserId = "hub-user-a" };
        var first = Admission(remote);
        var second = Admission(remote);
        HorizonArtifactRequestReceipt? winner = null;
        remote.BeforeHeadPost = () => winner = second.AdmitPrivateOriginScene(request);
        var result = first.AdmitPrivateOriginScene(request);
        Assert.NotNull(winner);
        Assert.Equal(JsonSerializer.Serialize(winner), JsonSerializer.Serialize(result));
        Assert.Equal(1, remote.HeadPosts);
    }

    [Fact]
    public void Changed_scene_consent_or_disabled_capability_cannot_reuse_or_replace_admission()
    {
        using var chapters = Prepare();
        using var remote = new TeableRevisionStoreTests.Remote();
        var bridge = new OriginChapterSceneRequestBridge(chapters);
        var request = bridge.Compose("owner-a", "request", Sha(Prose), Prose, "Scene", true, () => true)
            with { UserId = "hub-user-a" };
        Admission(remote).AdmitPrivateOriginScene(request);
        var changed = bridge.Compose("owner-a", "request", Sha(Prose), Prose, "Different scene description", true, () => true)
            with { UserId = "hub-user-a" };
        Assert.Throws<InvalidOperationException>(() => Admission(remote).AdmitPrivateOriginScene(changed));
        Assert.Throws<InvalidOperationException>(() => Admission(remote).AdmitPrivateOriginScene(request with { ExternalProcessingConsent = false }));
        Assert.Throws<InvalidOperationException>(() => Admission(remote, enabled: false).AdmitPrivateOriginScene(request));
        Assert.Equal(1, remote.HeadPosts);
    }

    [Theory]
    [InlineData("owner")]
    [InlineData("digest")]
    [InlineData("excerpt")]
    [InlineData("consent")]
    [InlineData("revocation")]
    public void Wrong_owner_stale_text_unapproved_excerpt_or_revocation_cannot_compose(string change)
    {
        using var service = Prepare();
        int checks = 0;
        Assert.ThrowsAny<Exception>(() => new OriginChapterSceneRequestBridge(service).Compose(
            change == "owner" ? "other-owner" : "owner-a", "request", change == "digest" ? new string('f', 64) : Sha(Prose),
            change == "excerpt" ? "Invented future military career." : Prose, "Scene", change != "consent",
            () => change != "revocation" || ++checks == 1));
    }

    public void Dispose()
    {
        if (Directory.Exists(root)) Directory.Delete(root, recursive: true);
    }
}
