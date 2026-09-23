using System.Net;
using System.Text;
using System.Text.Json.Nodes;
using Chummer.Control.Contracts.Support;
using Chummer.Run.Api;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.Services.Support;
using Chummer.Storage.Teable;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;
using Remote = Chummer.Tests.TeableRevisionStoreTests.Remote;

namespace Chummer.Tests;

public sealed class SupportTeablePersistenceTests : IDisposable
{
    private readonly string _root = Path.Combine(Path.GetTempPath(), "support-teable-" + Guid.NewGuid().ToString("N"));
    private IConfiguration Configuration(bool primary = true) => new ConfigurationBuilder().AddInMemoryCollection(
        new Dictionary<string, string?>
        {
            ["CHUMMER_SUPPORT_STORAGE_PROVIDER"] = primary ? "teable" : "local",
            ["CHUMMER_SUPPORT_STORE_PATH"] = Path.Combine(_root, "support.json"),
            ["CHUMMER_SUPPORT_ATTACHMENT_ROOT"] = Path.Combine(_root, "attachments"),
            ["CHUMMER_COMMUNITY_STORE_PATH"] = Path.Combine(_root, "community.json")
        }).Build();

    private SupportStore Store(Remote remote) => new(Configuration(), NullLogger<SupportStore>.Instance, remote.Store());
    private SupportAttachmentStorageService Attachments(SupportStore store) => new(Configuration(store.IsPrimary), store);
    private SupportCaseService Cases(SupportStore store) => new(store, Attachments(store),
        new RewardService(new CommunityStore(Configuration(false), NullLogger<CommunityStore>.Instance)),
        new SupportProgressEmailWorkflowService(new HttpClient(new NoExternalCalls()), Configuration(),
            NullLogger<SupportProgressEmailWorkflowService>.Instance), NullLogger<SupportCaseService>.Instance);
    private static SupportCaseSubmitRequest Request(string title = "Synthetic private case") => new(
        SupportCaseKinds.BugReport, title, "Synthetic summary", "Synthetic private detail",
        Source: SupportCaseSourceKinds.HubAccount);
    private SupportCaseProjection Submit(SupportStore store, string title = "Synthetic private case", bool attachment = false)
        => Cases(store).Submit("synthetic-user", "synthetic-subject", Request(title),
            attachment ? [new("debug.log", "text/plain", Encoding.UTF8.GetBytes("synthetic private attachment"))] : null);
    private static CrashEnvelope Crash(string id) => new(id, "android", "0.1.0-test", ".NET 10", "Android", "ARM64",
        "synthetic-fingerprint", "System.Exception", "synthetic exception", "synthetic detail", DateTimeOffset.UtcNow);
    private CrashSupportService Crashes(SupportStore store) => new(store, Cases(store), null!, NullLogger<CrashSupportService>.Instance);

    [Fact]
    public void Cold_restore_preserves_case_attachment_bytes_and_reporter_access_without_local_files()
    {
        using var remote = new Remote();
        using var writer = Store(remote);
        var saved = Submit(writer, attachment: true);
        var attachment = Assert.Single(saved.Attachments!);
        Assert.Equal(2, remote.HeadPosts); // one immutable blob, one case snapshot
        using var cold = Store(remote);
        var reader = Cases(cold);
        var restored = reader.GetForReporter(saved.CaseId, "synthetic-user", "synthetic-subject")!;
        Assert.Equal(System.Text.Json.JsonSerializer.Serialize(saved), System.Text.Json.JsonSerializer.Serialize(restored));
        Assert.Null(reader.GetForReporter(saved.CaseId, "other-user", "other-subject"));
        Assert.Null(reader.OpenAttachmentForReporter(saved.CaseId, attachment.AttachmentId, "other-user", "other-subject"));
        var download = reader.OpenAttachmentForReporter(saved.CaseId, attachment.AttachmentId, "synthetic-user", "synthetic-subject");
        Assert.NotNull(download);
        using var stream = download.Value.Stream;
        using var text = new StreamReader(stream);
        Assert.Equal("synthetic private attachment", text.ReadToEnd());
        Assert.Equal("debug.log", download.Value.FileName);
        Assert.False(Directory.Exists(_root));
    }

    [Fact]
    public void Current_reporter_change_is_observed_by_existing_service_and_download()
    {
        using var remote = new Remote();
        using var old = Store(remote);
        var original = Submit(old, attachment: true);
        var reader = Cases(old);
        using var newer = Store(remote);
        using (newer.Enter())
        {
            newer.CasesById[original.CaseId] = newer.CasesById[original.CaseId] with
                { ReporterUserId = "new-user", ReporterSubjectId = "new-subject" };
            newer.PersistLocked();
        }
        Assert.Null(reader.GetForReporter(original.CaseId, "synthetic-user", "synthetic-subject"));
        Assert.Null(reader.OpenAttachmentForReporter(original.CaseId, original.Attachments![0].AttachmentId,
            "synthetic-user", "synthetic-subject"));
        Assert.NotNull(reader.GetForReporter(original.CaseId, "new-user", "new-subject"));
    }

    [Fact]
    public void Crash_case_indexes_commit_once_and_remain_idempotent_after_cold_restore()
    {
        using var remote = new Remote();
        using var writer = Store(remote);
        var result = Crashes(writer).Submit(Crash("crash-synthetic"));
        Assert.Equal(1, remote.HeadPosts);
        using var cold = Store(remote);
        var reopened = Crashes(cold).Submit(Crash("crash-synthetic"));
        Assert.Equal(result.Incident.IncidentId, reopened.Incident.IncidentId);
        Assert.Equal(1, remote.HeadPosts);
        Assert.Single(Cases(cold).ListForAutomation().Items);
        var second = Crashes(cold).Submit(Crash("crash-synthetic-2"));
        Assert.Equal(2, second.Cluster.OccurrenceCount);
        Assert.Equal(2, remote.HeadPosts);
        using var final = Store(remote);
        Assert.Equal(2, Assert.Single(Crashes(final).ListClusters().Items).OccurrenceCount);
        Assert.Single(Cases(final).ListForAutomation().Items);
        Assert.False(Directory.Exists(_root));
    }

    [Fact]
    public void Competing_case_transition_rejects_loser_and_requires_cold_reconciliation()
    {
        using var remote = new Remote();
        using var first = Store(remote);
        var saved = Submit(first);
        using var second = Store(remote);
        remote.BeforeHeadPost = () => Cases(second).Transition(saved.CaseId, new(SupportCaseStatuses.Fixed, "winning update"));
        Assert.Throws<TeableRevisionConflictException>(() => Cases(first).Transition(saved.CaseId,
            new(SupportCaseStatuses.AwaitingEvidence, "losing update")));
        Assert.Throws<InvalidOperationException>(() => Cases(first).ListForAutomation());
        using var cold = Store(remote);
        Assert.Equal(SupportCaseStatuses.Fixed, Assert.Single(Cases(cold).ListForAutomation().Items).Status);
    }

    [Fact]
    public void Uncertain_case_commit_cold_restores_without_replaying_submission()
    {
        using var remote = new Remote();
        using var writer = Store(remote);
        remote.CommitThenFailHard = true;
        Assert.Throws<IOException>(() => Submit(writer));
        int writes = remote.HeadPosts;
        Assert.Throws<InvalidOperationException>(() => Submit(writer));
        using var cold = Store(remote);
        Assert.Single(Cases(cold).ListForReporter("synthetic-user", "synthetic-subject").Items);
        Assert.Equal(writes, remote.HeadPosts);
    }

    [Fact]
    public void Nested_read_does_not_discard_pending_support_state()
    {
        using var remote = new Remote();
        using var store = Store(remote);
        var saved = Submit(store);
        using (store.Enter())
        {
            store.CasesById[saved.CaseId] = saved with { Summary = "pending summary" };
            Assert.Equal("pending summary", Cases(store).GetForReporter(saved.CaseId, "synthetic-user", "synthetic-subject")!.Summary);
            store.PersistLocked();
        }
        using var cold = Store(remote);
        Assert.Equal("pending summary", Assert.Single(Cases(cold).ListForAutomation().Items).Summary);
    }

    [Fact]
    public void Invalid_attachment_batch_writes_nothing_and_orphan_blobs_are_not_downloadable()
    {
        using var remote = new Remote();
        using var store = Store(remote);
        var attachments = Attachments(store);
        Assert.Throws<ArgumentException>(() => attachments.SaveAttachments("synthetic-case",
            [new("valid.log", "text/plain", [1]), new("invalid.exe", "application/octet-stream", [2])]));
        Assert.Equal(0, remote.HeadPosts);
        var orphan = Assert.Single(attachments.SaveAttachments("synthetic-case", [new("orphan.log", "text/plain", [1, 2, 3])]));
        Assert.Null(attachments.TryOpenAttachment("synthetic-case", orphan.AttachmentId));
        using var cold = Store(remote);
        Assert.Null(Attachments(cold).TryOpenAttachment("other-case", orphan.AttachmentId));
        Assert.Empty(Cases(cold).ListForAutomation().Items);
        Assert.False(Directory.Exists(_root));
    }

    [Fact]
    public async Task Attachment_revision_replacement_is_rejected_instead_of_served()
    {
        using var remote = new Remote();
        using var store = Store(remote);
        var saved = Submit(store, attachment: true);
        string blobStream = remote.Rows.Values.Select(row => row["stream"]!.GetValue<string>())
            .First(value => value.StartsWith("support-attachment-", StringComparison.Ordinal));
        using var transport = remote.Store();
        var head = (await transport.ReadAsync(blobStream))!;
        await transport.CompareExchangeAsync(blobStream, head, Guid.NewGuid(), head.Bytes);
        Assert.Throws<InvalidDataException>(() => Cases(store).OpenAttachmentForReporter(saved.CaseId,
            saved.Attachments![0].AttachmentId, "synthetic-user", "synthetic-subject"));
    }

    [Fact]
    public void Download_retains_extension_based_mime_and_does_not_trust_upload_content_type()
    {
        using var remote = new Remote();
        using var store = Store(remote);
        var saved = Cases(store).Submit("synthetic-user", "synthetic-subject", Request(),
            [new("untrusted.txt", "text/html", Encoding.UTF8.GetBytes("<script>synthetic</script>"))]);
        var attachment = Assert.Single(saved.Attachments!);
        var download = Cases(store).OpenAttachmentForReporter(saved.CaseId, attachment.AttachmentId,
            "synthetic-user", "synthetic-subject");
        Assert.NotNull(download);
        using var stream = download.Value.Stream;
        Assert.Equal("text/plain", download.Value.ContentType);
    }

    [Fact]
    public void Uncertain_attachment_commit_does_not_expose_a_partial_case()
    {
        using var remote = new Remote();
        using var store = Store(remote);
        remote.CommitThenFailHard = true;
        Assert.Throws<IOException>(() => Submit(store, attachment: true));
        int writes = remote.HeadPosts;
        using var cold = Store(remote);
        Assert.Empty(Cases(cold).ListForAutomation().Items);
        Assert.Equal(writes, remote.HeadPosts);
        Assert.False(Directory.Exists(_root));
    }

    [Theory]
    [InlineData("schema")]
    [InlineData("missing-map")]
    [InlineData("identity")]
    [InlineData("index")]
    [InlineData("duplicate-case-key")]
    public async Task Malformed_primary_state_fails_without_reset_or_local_fallback(string corruption)
    {
        using var remote = new Remote();
        using var store = Store(remote);
        var saved = Submit(store);
        using var transport = remote.Store();
        var head = (await transport.ReadAsync("support"))!;
        var payload = JsonNode.Parse(head.Bytes)!;
        var snapshot = payload["snapshot"]!;
        if (corruption == "schema") payload["schema"] = "foreign";
        else if (corruption == "missing-map") snapshot["casesById"] = null;
        else if (corruption == "identity") snapshot["casesById"]![saved.CaseId]!["caseId"] = "other-case";
        else if (corruption == "index") snapshot["caseIdByClusterKey"]![saved.ClusterKey] = "absent-case";
        else snapshot["casesById"]![saved.CaseId.ToUpperInvariant()] = snapshot["casesById"]![saved.CaseId]!.DeepClone();
        await transport.CompareExchangeAsync("support", head, Guid.NewGuid(), Encoding.UTF8.GetBytes(payload.ToJsonString()));
        int writes = remote.HeadPosts;
        Assert.Throws<InvalidDataException>(() => Store(remote));
        Assert.Equal(writes, remote.HeadPosts);
        Assert.False(Directory.Exists(_root));
    }

    [Fact]
    public void Outage_preserves_old_local_data_but_never_uses_it_as_primary()
    {
        using var local = new SupportStore(Configuration(false), NullLogger<SupportStore>.Instance);
        var old = Submit(local, "Local-only case", attachment: true);
        byte[] localBytes = File.ReadAllBytes(local.StoragePath);
        using var remote = new Remote();
        using var primary = Store(remote);
        var current = Submit(primary, "Remote-only case", attachment: true);
        Assert.Null(Cases(primary).GetForReporter(old.CaseId, "synthetic-user", "synthetic-subject"));
        remote.FailReads = true;
        Assert.Throws<HttpRequestException>(() => Cases(primary).OpenAttachmentForReporter(current.CaseId,
            current.Attachments![0].AttachmentId, "synthetic-user", "synthetic-subject"));
        Assert.Throws<InvalidOperationException>(() => Cases(primary).ListForAutomation());
        Assert.Equal(localBytes, File.ReadAllBytes(local.StoragePath));
    }

    [Fact]
    public async Task Erasure_rejects_before_journal_or_other_account_side_effects()
    {
        using var remote = new Remote();
        using var primary = Store(remote);
        Submit(primary, attachment: true);
        int writes = remote.HeadPosts;
        Assert.Throws<NotSupportedException>(() => primary.EraseReporter("synthetic-user", "synthetic-subject"));
        // All later dependencies are deliberately unavailable: preflight must
        // reject before account lookup, journal, hosted deletion or identity.
        var erasure = new AccountErasureService(null!, null!, primary, null!, null!, null!, null!, Configuration());
        await Assert.ThrowsAsync<NotSupportedException>(() => erasure.EraseAsync("synthetic-subject", CancellationToken.None));
        Assert.Equal(writes, remote.HeadPosts);
        using var cold = Store(remote);
        Assert.Single(Cases(cold).ListForAutomation().Items);
    }

    [Fact]
    public void Primary_requires_explicit_matching_credentials_and_shared_attachment_backend()
    {
        Assert.Throws<InvalidOperationException>(() => new SupportStore(Configuration(), NullLogger<SupportStore>.Instance));
        Assert.Throws<InvalidOperationException>(() => new SupportAttachmentStorageService(Configuration()));
        var services = new ServiceCollection().AddLogging().AddSingleton(Configuration());
        services.AddHubControlAndSupportContext();
        using var provider = services.BuildServiceProvider();
        Assert.Throws<InvalidOperationException>(() => provider.GetRequiredService<SupportStore>());
        using var remote = new Remote();
        using var primary = Store(remote);
        Assert.Throws<InvalidOperationException>(() => new SupportCaseService(primary,
            new SupportAttachmentStorageService(Configuration(false)), null!, null!, NullLogger<SupportCaseService>.Instance));
        Assert.Throws<InvalidOperationException>(() => primary.Gate);
        Assert.Throws<InvalidOperationException>(() => primary.PersistLocked());
    }

    private sealed class NoExternalCalls : HttpMessageHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
            => throw new InvalidOperationException("No email/provider request is authorized by these synthetic tests.");
    }

    public void Dispose()
    {
        if (Directory.Exists(_root)) Directory.Delete(_root, recursive: true);
    }
}
