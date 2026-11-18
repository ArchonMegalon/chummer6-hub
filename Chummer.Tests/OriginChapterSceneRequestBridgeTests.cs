using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.Services.Teable;
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

    private OriginChapterAuthoringService Prepare(bool accepted = true, OriginChapterAuthoringService? service = null)
    {
        service ??= Service();
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
        Assert.Equal("chummer.origin.chapter-scene/v2", payload.RootElement.GetProperty("schema").GetString());
        Assert.Equal(identity, payload.RootElement.GetProperty("referenceSceneId").GetString());
        Assert.Equal(Sha(string.Join('\0', Sha("owner-a"), "workspace", "origin-protagonist/v1")),
            payload.RootElement.GetProperty("protagonistId").GetString());
        Assert.Equal(Sha(Prose), payload.RootElement.GetProperty("textDigest").GetString());
        Assert.Contains(Prose, payload.RootElement.GetProperty("prompt").GetString());
        Assert.Equal(before, JsonSerializer.Serialize(service.Get("owner-a", "request")));
    }

    private static OriginChapterAuthoringJob Continue(OriginChapterAuthoringService service,
        OriginChapterAuthoringJob previous, string chapter, string stage, string prose)
    {
        var source = previous.Source with { ChapterId = chapter, ChapterDigest = Sha(chapter),
            AcceptedDecisionId = chapter, Facts = [.. previous.Source.Facts, new(chapter, chapter, stage)] };
        var job = service.Create("owner-a", new(chapter, source, true) { Previous = new(previous.RequestId,
            previous.SourceDigest, previous.ProviderReceiptDigest!, previous.ReaderAcceptedTextDigest!) }, () => true);
        var work = Assert.Single(service.PendingForWorker(10));
        service.AdmitForWorker(work.WorkId, job.SourceDigest, "admission");
        service.CompleteForWorker(work.WorkId, job.SourceDigest, "admission", prose, Sha(prose + "receipt"));
        return service.AcceptReading("owner-a", job.RequestId, job.SourceDigest, Sha(prose + "receipt"),
            Sha(prose), true, () => true);
    }

    [Fact]
    public void Automatic_book_scene_chooses_accepted_prose_and_retains_privately_without_claiming_image_review()
    {
        using var service = Prepare();
        var before = JsonSerializer.Serialize(service.Get("owner-a", "request"));
        var request = new OriginChapterSceneRequestBridge(service).ComposeAutomatic("owner-a", "request", Sha(Prose), true, () => true);
        var capability = new HorizonCapabilityService(new ConfigurationBuilder().Build()).GetCapability("origin-dossier", "origin-dossier-media");
        var composed = new HorizonGovernedRenderRequestComposerService().Compose(capability, request.SourceRef, request.GovernedRenderRequest!);
        Assert.True(composed.Accepted);
        Assert.Equal("private", composed.Contract!.Audience);
        var artifact = Assert.Single(composed.Contract.Artifacts);
        Assert.False(artifact.RequiresApproval);
        Assert.False(artifact.PersistOnApproval);
        Assert.False(artifact.AllowPersistentPinning);
        using var payload = JsonDocument.Parse(artifact.Payload);
        Assert.Equal("chummer.origin.chapter-scene/v3", payload.RootElement.GetProperty("schema").GetString());
        Assert.Equal("automatic-private-book/v1", payload.RootElement.GetProperty("insertionPolicy").GetString());
        Assert.Equal("Kapitelillustration: Synthetic", payload.RootElement.GetProperty("altText").GetString());
        Assert.Contains(Prose, payload.RootElement.GetProperty("prompt").GetString());
        Assert.Equal(composed.Contract.WorkItemId, payload.RootElement.GetProperty("referenceSceneId").GetString());
        Assert.Equal(before, JsonSerializer.Serialize(service.Get("owner-a", "request")));
        var audit = new HorizonArtifactRequestService(new(new ConfigurationBuilder().Build()))
            .BuildRequest(request, requireEnabledCapability: false);
        Assert.Equal("accepted", audit.Status);
        Assert.Null(audit.Quota); // Compose is not permission to execute a renderer.
    }

    [Fact]
    public void Automatic_scene_uses_one_fresh_authorization_pair_for_its_accepted_chapter()
    {
        using var service = Prepare();
        int checks = 0;
        var request = new OriginChapterSceneRequestBridge(service).ComposeAutomatic(
            "owner-a", "request", Sha(Prose), true, () => { checks++; return true; });
        Assert.NotNull(request.GovernedRenderRequest);
        // Automatic excerpt selection and manual composition must not each
        // traverse the same chapter through another remote authority pair.
        Assert.Equal(2, checks);
        var manual = new OriginChapterSceneRequestBridge(service).Compose("owner-a", "request", Sha(Prose),
            Prose, "Kapitelillustration: Synthetic", true, () => true);
        var expected = System.Text.Json.Nodes.JsonNode.Parse(Assert.Single(manual.GovernedRenderRequest!.Artifacts!).Payload)!;
        expected["schema"] = "chummer.origin.chapter-scene/v3";
        expected["insertionPolicy"] = "automatic-private-book/v1";
        Assert.Equal(expected.ToJsonString(new JsonSerializerOptions(JsonSerializerDefaults.Web)),
            Assert.Single(request.GovernedRenderRequest.Artifacts!).Payload);
    }

    [Theory]
    [InlineData(1)]
    [InlineData(2)]
    public void Automatic_scene_fails_if_authority_is_revoked_before_read_or_before_return(int revokeAt)
    {
        using var service = Prepare();
        int checks = 0;
        Assert.Throws<UnauthorizedAccessException>(() => new OriginChapterSceneRequestBridge(service)
            .ComposeAutomatic("owner-a", "request", Sha(Prose), true, () => ++checks < revokeAt));
        Assert.Equal(revokeAt, checks);
    }

    [Theory]
    [InlineData(1)]
    [InlineData(2)]
    public void Automatic_continuation_keeps_fresh_authority_before_read_and_before_return(int revokeAt)
    {
        using var service = Prepare();
        var next = Continue(service, service.Get("owner-a", "request")!, "school", "School stage", "A school courtyard.");
        int checks = 0;
        Assert.Throws<UnauthorizedAccessException>(() => new OriginChapterSceneRequestBridge(service)
            .ComposeAutomatic("owner-a", next.RequestId, next.ReaderAcceptedTextDigest!, true, () => ++checks < revokeAt));
        Assert.Equal(revokeAt, checks);
    }

    [Fact]
    public void Automatic_continuation_checks_authority_once_around_the_entire_read_only_chain()
    {
        using var service = Prepare();
        var opening = service.Get("owner-a", "request")!;
        var school = Continue(service, opening, "school", "School stage", "A school courtyard.");
        var next = Continue(service, school, "college", "College stage", "A university laboratory.");
        int checks = 0;
        var request = new OriginChapterSceneRequestBridge(service).ComposeAutomatic(
            "owner-a", next.RequestId, next.ReaderAcceptedTextDigest!, true, () => { checks++; return true; });
        Assert.Equal(2, checks); // Not one remote install probe per predecessor.
        using var payload = JsonDocument.Parse(Assert.Single(request.GovernedRenderRequest!.Artifacts!).Payload);
        string firstScene = new OriginChapterSceneRequestBridge(service).ResolveIdentity(
            "owner-a", opening.RequestId, opening.ReaderAcceptedTextDigest!, () => true);
        Assert.Equal(firstScene, payload.RootElement.GetProperty("referenceSceneId").GetString());
        Assert.Contains(next.DraftText!, payload.RootElement.GetProperty("prompt").GetString());
    }

    [Fact]
    public void Revocation_during_a_remote_predecessor_read_cannot_release_a_scene_packet()
    {
        using var remote = new TeableRevisionStoreTests.Remote();
        using var service = Prepare(service: new OriginChapterAuthoringService(
            new ConfigurationBuilder().AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_RUNTIME_STATE_ROOT"] = root,
                ["CHUMMER_ORIGIN_CHAPTER_STORAGE_PROVIDER"] = "teable"
            }).Build(), new TeableOriginChapterStorage(remote.Store())));
        var opening = service.Get("owner-a", "request")!;
        var school = Continue(service, opening, "school", "School stage", "A school courtyard.");
        var next = Continue(service, school, "college", "College stage", "A university laboratory.");
        string openingWorkId = Sha(JsonSerializer.Serialize("owner-a")) + "." + Sha(JsonSerializer.Serialize("request"));
        string openingStream = TeableOriginChapterStorage.JobStream(openingWorkId);
        int writes = remote.HeadPosts, checks = 0;
        bool authorized = true, predecessorRead = false;
        remote.BeforeRecordReadResponse = (row, _) =>
        {
            if (row["stream"]!.GetValue<string>() == openingStream)
            {
                predecessorRead = true;
                authorized = false;
            }
            return Task.CompletedTask;
        };
        Assert.Throws<UnauthorizedAccessException>(() => new OriginChapterSceneRequestBridge(service)
            .ComposeAutomatic("owner-a", next.RequestId, next.ReaderAcceptedTextDigest!, true,
                () => { checks++; return authorized; }));
        Assert.True(predecessorRead);
        Assert.Equal(2, checks);
        Assert.Equal(writes, remote.HeadPosts);
    }

    [Fact]
    public void Automatic_book_scene_still_requires_current_owner_accepted_text_and_image_consent()
    {
        using var service = Prepare(false);
        var bridge = new OriginChapterSceneRequestBridge(service);
        Assert.Throws<ArgumentException>(() => bridge.ComposeAutomatic("owner-a", "request", Sha(Prose), false, () => true));
        Assert.Throws<UnauthorizedAccessException>(() => bridge.ComposeAutomatic("owner-a", "request", Sha(Prose), true, () => false));
        Assert.Throws<KeyNotFoundException>(() => bridge.ComposeAutomatic("owner-b", "request", Sha(Prose), true, () => true));
        Assert.Throws<InvalidOperationException>(() => bridge.ComposeAutomatic("owner-a", "request", Sha(Prose), true, () => true));
    }

    [Fact]
    public void Automatic_book_mode_cannot_relabel_an_existing_paid_manual_image_order()
    {
        using var chapters = Prepare();
        using var remote = new TeableRevisionStoreTests.Remote();
        var bridge = new OriginChapterSceneRequestBridge(chapters);
        var original = bridge.Compose("owner-a", "request", Sha(Prose), Prose, "Scene", true, () => true) with { UserId = "hub-user-a" };
        Admission(remote).AdmitPrivateOriginScene(original);
        var automatic = bridge.ComposeAutomatic("owner-a", "request", Sha(Prose), true, () => true) with { UserId = "hub-user-a" };
        Assert.Throws<InvalidOperationException>(() => Admission(remote).AdmitPrivateOriginScene(automatic));
        Assert.Equal(1, remote.HeadPosts);
    }

    [Fact]
    public void Automatic_scene_admission_keeps_the_existing_durable_allowance_and_no_replay_boundary()
    {
        using var chapters = Prepare();
        using var remote = new TeableRevisionStoreTests.Remote();
        var request = new OriginChapterSceneRequestBridge(chapters).ComposeAutomatic(
            "owner-a", "request", Sha(Prose), true, () => true) with { UserId = "hub-user-a" };
        var first = Admission(remote).AdmitPrivateOriginScene(request);
        var reopened = Admission(remote).AdmitPrivateOriginScene(request);
        Assert.Equal(JsonSerializer.Serialize(first), JsonSerializer.Serialize(reopened));
        Assert.NotNull(first.Quota);
        Assert.Equal(1, remote.HeadPosts);
        Assert.Throws<InvalidOperationException>(() => Admission(remote, enabled: false).AdmitPrivateOriginScene(request));
        Assert.Throws<InvalidOperationException>(() => Admission(remote).AdmitPrivateOriginScene(request with { ExternalProcessingConsent = false }));
        Assert.Equal(1, remote.HeadPosts);
    }

    [Fact]
    public void Every_life_stage_uses_the_original_protagonist_reference_after_cold_reopen()
    {
        string anchor;
        string protagonist;
        using (var service = Prepare())
        {
            var bridge = new OriginChapterSceneRequestBridge(service);
            var first = bridge.Compose("owner-a", "request", Sha(Prose), Prose, "Childhood", true, () => true);
            using var rootPayload = JsonDocument.Parse(Assert.Single(first.GovernedRenderRequest!.Artifacts!).Payload);
            anchor = rootPayload.RootElement.GetProperty("referenceSceneId").GetString()!;
            protagonist = rootPayload.RootElement.GetProperty("protagonistId").GetString()!;
            var teen = Continue(service, service.Get("owner-a", "request")!, "school", "A teenager at school.",
                "As a teenager, she crossed the school courtyard.");
            Continue(service, teen, "work", "A young adult at her first job.",
                "Now a young adult, she stepped into the workshop.");
        }
        using var cold = Service();
        foreach (var chapter in new[] { "school", "work" })
        {
            var job = cold.Get("owner-a", chapter)!;
            var request = new OriginChapterSceneRequestBridge(cold).Compose("owner-a", chapter,
                job.ReaderAcceptedTextDigest!, job.DraftText!, "Scene", true, () => true);
            using var payload = JsonDocument.Parse(Assert.Single(request.GovernedRenderRequest!.Artifacts!).Payload);
            Assert.Equal(anchor, payload.RootElement.GetProperty("referenceSceneId").GetString());
            Assert.Equal(protagonist, payload.RootElement.GetProperty("protagonistId").GetString());
            string prompt = payload.RootElement.GetProperty("prompt").GetString()!;
            Assert.Contains("Keep the SAME person", prompt);
            Assert.Contains(job.Source.Facts.Last().Text, prompt);
            Assert.Contains(job.DraftText!, prompt);
            Assert.DoesNotContain("Invented future", prompt);
            Assert.NotEqual(anchor, request.GovernedRenderRequest.WorkItemId);
        }
    }

    [Fact]
    public void Unicode_protagonist_brief_and_stage_stay_bounded_without_breaking_characters()
    {
        using var service = Service();
        string text = string.Concat(Enumerable.Repeat("🌲", 700));
        var source = new OriginChapterSource("workspace", "chapter", Sha("chapter"), "decision", "de-DE",
            new string('名', 256), [new("metatype", "decision", new string('界', 2048)),
                new("player-story-brief-profile", "profile", new string('界', 2048))]);
        var job = service.Create("owner-a", new("request", source, true), () => true);
        var work = Assert.Single(service.PendingForWorker(10));
        service.AdmitForWorker(work.WorkId, job.SourceDigest, "admission");
        service.CompleteForWorker(work.WorkId, job.SourceDigest, "admission", text, Sha("receipt"));
        service.AcceptReading("owner-a", "request", job.SourceDigest, Sha("receipt"), Sha(text), true, () => true);
        var request = new OriginChapterSceneRequestBridge(service).Compose("owner-a", "request", Sha(text), text,
            "Scene", true, () => true);
        using var payload = JsonDocument.Parse(Assert.Single(request.GovernedRenderRequest!.Artifacts!).Payload);
        string prompt = payload.RootElement.GetProperty("prompt").GetString()!;
        Assert.True(Encoding.UTF8.GetByteCount(prompt) <= 4096);
        Assert.DoesNotContain("\uFFFD", prompt);
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

    private IConfiguration AdmissionConfig(bool enabled = true, Dictionary<string, string?>? overrides = null) => new ConfigurationBuilder().AddInMemoryCollection(
        new Dictionary<string, string?>
        {
            ["CHUMMER_HORIZON_ARTIFACT_USAGE_STORAGE_PROVIDER"] = "teable",
            ["CHUMMER_HORIZON_REQUEST_RECEIPT_STORAGE_PROVIDER"] = "teable",
            ["CHUMMER_MYFIRSTBOOK_USAGE_STORAGE_PROVIDER"] = "teable",
            ["CHUMMER_BILLING_MEMBERSHIP_STORAGE_PROVIDER"] = "teable",
            ["HorizonCapabilities:origin-dossier:origin-dossier-media:Enabled"] = enabled.ToString(),
            ["HorizonCapabilities:origin-dossier:origin-dossier-media:FreeWeeklyLimit"] = "2"
        }).AddInMemoryCollection(overrides ?? []).Build();

    private HorizonArtifactRequestService Admission(TeableRevisionStoreTests.Remote remote, bool enabled = true,
        Dictionary<string, string?>? overrides = null)
    {
        var config = AdmissionConfig(enabled, overrides);
        var billing = new BrilliantDirectoriesBillingService(new(config, primary: remote.Store()),
            new(config, primary: remote.Store()), config);
        return new(new(config), new(new(config, remote.Store()), new(config), billing), new(config, remote.Store()));
    }

    private static Dictionary<string, string?> Sponsored(DateTimeOffset now)
    {
        var monday = new DateTimeOffset(now.UtcDateTime.Date, TimeSpan.Zero)
            .AddDays(-((7 + (int)now.DayOfWeek - (int)DayOfWeek.Monday) % 7));
        return new()
        {
            ["HorizonCapabilities:origin-dossier:origin-dossier-media:FreeWeeklyLimit"] = "0",
            ["CHUMMER_ORIGIN_SCENE_SPONSOR_USER_SHA256"] = Sha("HUB-USER-A"),
            ["CHUMMER_ORIGIN_SCENE_SPONSOR_LIMIT"] = "1",
            ["CHUMMER_ORIGIN_SCENE_SPONSOR_WEEK_START_UTC"] = monday.ToString("yyyy-MM-dd'T'HH:mm:ss'Z'"),
            ["CHUMMER_ORIGIN_SCENE_SPONSOR_EXPIRES_AT_UTC"] = monday.AddDays(7).ToString("yyyy-MM-dd'T'HH:mm:ss'Z'")
        };
    }

    [Fact]
    public void Private_sponsored_scene_is_not_membership_and_cold_reopen_cannot_charge_twice()
    {
        using var chapters = Prepare();
        using var remote = new TeableRevisionStoreTests.Remote();
        var request = new OriginChapterSceneRequestBridge(chapters).Compose("owner-a", "request", Sha(Prose),
            Prose, "Scene", true, () => true) with { UserId = "hub-user-a" };
        var config = Sponsored(DateTimeOffset.UtcNow);
        var first = Admission(remote, overrides: config).AdmitPrivateOriginScene(request);
        Assert.False(first.Quota!.SupporterActive);
        Assert.Equal("sponsored_test", first.Quota.AllowanceTier);
        Assert.Equal("operator_approved_private_scene_trial", first.Quota.EntitlementBasis);
        Assert.Equal("private_origin_scene", first.Quota.EntitlementScope);
        Assert.Equal(1, first.Quota.WindowUsed);
        Assert.Equal(0, first.Quota.WindowRemaining);
        var restored = Admission(remote, overrides: config).AdmitPrivateOriginScene(request);
        Assert.Equal(JsonSerializer.Serialize(first), JsonSerializer.Serialize(restored));
        Assert.Equal(1, remote.HeadPosts);
        // Removing the trial does not remove an already-paid exact order or
        // reset the usage ledger. A new scene still has no remaining allowance.
        config.Remove("CHUMMER_ORIGIN_SCENE_SPONSOR_LIMIT");
        Assert.Equal(JsonSerializer.Serialize(first), JsonSerializer.Serialize(
            Admission(remote, overrides: config).AdmitPrivateOriginScene(request)));
        var otherId = new string('f', 64);
        var next = request with { SourceRef = "origin-dossier:scene:" + otherId,
            GovernedRenderRequest = request.GovernedRenderRequest! with { WorkItemId = otherId } };
        var denied = Admission(remote, overrides: Sponsored(DateTimeOffset.UtcNow)).BuildRequest(next, consumeQuota: true);
        Assert.Equal("blocked", denied.Status);
        Assert.Contains("artifact allowance", denied.BlockedReasons);
    }

    [Theory]
    [InlineData("owner")]
    [InlineData("public")]
    [InlineData("consent")]
    [InlineData("missing-limit")]
    [InlineData("zero")]
    [InlineData("oversized")]
    [InlineData("bad-owner")]
    [InlineData("wrong-week")]
    [InlineData("no-timezone")]
    [InlineData("expired")]
    [InlineData("future")]
    public void Sponsored_trial_does_not_admit_another_owner_visibility_or_invalid_window(string change)
    {
        using var chapters = Prepare();
        using var remote = new TeableRevisionStoreTests.Remote();
        var now = new DateTimeOffset(2026, 9, 26, 12, 0, 0, TimeSpan.Zero);
        var config = Sponsored(now);
        switch (change)
        {
            case "missing-limit": config.Remove("CHUMMER_ORIGIN_SCENE_SPONSOR_LIMIT"); break;
            case "zero": config["CHUMMER_ORIGIN_SCENE_SPONSOR_LIMIT"] = "0"; break;
            case "oversized": config["CHUMMER_ORIGIN_SCENE_SPONSOR_LIMIT"] = "9"; break;
            case "bad-owner": config["CHUMMER_ORIGIN_SCENE_SPONSOR_USER_SHA256"] = "not-a-digest"; break;
            case "wrong-week": config["CHUMMER_ORIGIN_SCENE_SPONSOR_WEEK_START_UTC"] = "2026-09-22T00:00:00Z"; break;
            case "no-timezone": config["CHUMMER_ORIGIN_SCENE_SPONSOR_EXPIRES_AT_UTC"] = "2026-09-27T00:00:00"; break;
            case "expired": config["CHUMMER_ORIGIN_SCENE_SPONSOR_EXPIRES_AT_UTC"] = "2026-09-26T12:00:00Z"; break;
            case "future": config = Sponsored(now.AddDays(7)); break;
        }
        var request = new OriginChapterSceneRequestBridge(chapters).Compose("owner-a", "request", Sha(Prose),
            Prose, "Scene", true, () => true) with
        {
            UserId = change == "owner" ? "hub-user-b" : "hub-user-a",
            Visibility = change == "public" ? "public" : "private",
            ExternalProcessingConsent = change != "consent"
        };
        var denied = Admission(remote, overrides: config).BuildRequest(request, now, consumeQuota: true);
        Assert.Equal("blocked", denied.Status);
        Assert.NotEmpty(denied.BlockedReasons);
        Assert.Equal(0, denied.Quota?.WindowUsed ?? 0);
    }

    [Fact]
    public void Sponsored_allowance_cannot_be_consumed_without_a_private_scene_receipt()
    {
        using var remote = new TeableRevisionStoreTests.Remote();
        var now = new DateTimeOffset(2026, 9, 26, 12, 0, 0, TimeSpan.Zero);
        var config = AdmissionConfig(overrides: Sponsored(now));
        var billing = new BrilliantDirectoriesBillingService(new(config, primary: remote.Store()),
            new(config, primary: remote.Store()), config);
        var quota = new HorizonArtifactQuotaService(new(config, remote.Store()), new(config), billing);
        var request = new HorizonArtifactQuotaRequest("hub-user-a", "origin-dossier", "origin-dossier-media");
        Assert.Equal(1, quota.GetQuota(request, now).WindowRemaining);
        Assert.Throws<InvalidOperationException>(() => quota.Consume(request, now));
        Assert.Equal(0, remote.HeadPosts);
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
    public void Retained_scene_lookup_is_exact_read_only_and_independent_of_current_allowance()
    {
        using var chapters = Prepare();
        using var remote = new TeableRevisionStoreTests.Remote();
        var request = new OriginChapterSceneRequestBridge(chapters).Compose("owner-a", "request", Sha(Prose),
            Prose, "Scene", true, () => true) with { UserId = "hub-user-a" };
        string asset = request.GovernedRenderRequest!.WorkItemId;
        Assert.Null(Admission(remote).FindPrivateOriginScene("hub-user-a", "owner-a", asset));
        var admitted = Admission(remote).AdmitPrivateOriginScene(request);
        var cold = Admission(remote, enabled: false, overrides: new()
            { ["HorizonCapabilities:origin-dossier:origin-dossier-media:FreeWeeklyLimit"] = "0" });
        Assert.Equal(JsonSerializer.Serialize(admitted), JsonSerializer.Serialize(
            cold.FindPrivateOriginScene("hub-user-a", "owner-a", asset)));
        Assert.Null(cold.FindPrivateOriginScene("other-user", "owner-a", asset));
        Assert.Null(cold.FindPrivateOriginScene("hub-user-a", "owner-a", new string('f', 64)));
        Assert.Throws<InvalidDataException>(() => cold.FindPrivateOriginScene("hub-user-a", "other-owner", asset));
        Assert.Equal(1, remote.HeadPosts);
        remote.FailReads = true;
        Assert.Throws<HttpRequestException>(() => cold.FindPrivateOriginScene("hub-user-a", "owner-a", asset));
        Assert.Throws<IOException>(() => new HorizonArtifactRequestService(new(AdmissionConfig()))
            .FindPrivateOriginScene("hub-user-a", "owner-a", asset));
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
