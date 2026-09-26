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
    public void Draft_provider_text_is_not_reader_acceptance()
    {
        using var service = Prepare(false);
        Assert.Throws<InvalidOperationException>(() => new OriginChapterSceneRequestBridge(service).Compose(
            "owner-a", "request", Sha(Prose), Prose, "Scene", true, () => true));
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
