using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api;
using Chummer.Run.Api.Services.Teable;
using Chummer.Run.Contracts.Community;
using Chummer.Storage.Teable;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Xunit;
using Remote = Chummer.Tests.TeableRevisionStoreTests.Remote;

namespace Chummer.Tests;

public sealed class OriginChapterTeablePersistenceTests : IDisposable
{
    private readonly string _root = Path.Combine(Path.GetTempPath(), "origin-teable-" + Guid.NewGuid().ToString("N"));
    private IConfiguration Configuration(string provider = "teable") => new ConfigurationBuilder().AddInMemoryCollection(
        new Dictionary<string, string?>
        {
            ["CHUMMER_RUNTIME_STATE_ROOT"] = _root,
            ["CHUMMER_ORIGIN_CHAPTER_STORAGE_PROVIDER"] = provider
        }).Build();
    private OriginChapterAuthoringService Service(Remote remote) => new(Configuration(), new(remote.Store()));
    private static OriginChapterAuthoringRequest Request(string id = "request-one") => new(id,
        new("runner", "chapter", new string('a', 64), "decision", "de", "Synthetic runner",
            [new("fact", "decision", "Selected a corporate school.")]), true);
    private static string Hash(string text) => Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(text)));
    private static bool Authorized() => true;

    [Fact]
    public void Primary_job_result_and_reader_acceptance_restore_without_local_files()
    {
        using var remote = new Remote();
        var job = Service(remote).Create("owner-a", Request(), Authorized);
        Assert.Equal(job.SourceDigest, Service(remote).Create("owner-a", Request(), Authorized).SourceDigest);
        Assert.Null(Service(remote).Get("owner-b", job.RequestId));
        Assert.Throws<InvalidOperationException>(() => Service(remote).Create("owner-a",
            Request() with { Source = Request().Source with { RunnerName = "Changed" } }, Authorized));
        var work = Assert.Single(Service(remote).PendingForWorker(20));
        Assert.True(Service(remote).AdmitForWorker(work.WorkId, job.SourceDigest, "execution-one").MayStartGeneration);
        Assert.False(Service(remote).AdmitForWorker(work.WorkId, job.SourceDigest, "execution-one").MayStartGeneration);
        const string text = "A synthetic chapter, not a provider result.";
        string receipt = new string('c', 64);
        Service(remote).CompleteForWorker(work.WorkId, job.SourceDigest, "execution-one", text, receipt);
        Assert.Equal(text, Service(remote).Get("owner-a", job.RequestId)!.DraftText);
        Assert.Throws<ArgumentException>(() => Service(remote).AcceptReading("owner-a", job.RequestId,
            job.SourceDigest, receipt, Hash(text), false, Authorized));
        Assert.Throws<InvalidOperationException>(() => Service(remote).AcceptReading("owner-a", job.RequestId,
            job.SourceDigest, receipt, Hash("Other text"), true, Authorized));
        Service(remote).AcceptReading("owner-a", job.RequestId, job.SourceDigest, receipt, Hash(text), true, Authorized);
        var cold = Service(remote).GetForWorker(work.WorkId);
        Assert.Equal(Hash(text), cold.Job.ReaderAcceptedTextDigest);
        Assert.Equal(work.BookRef, cold.BookRef);
        Assert.False(cold.Job.AffectsMechanics);
        Assert.False(cold.Job.PublicationAuthorized);
        Assert.Empty(Service(remote).PendingForWorker(20));
        Assert.False(Directory.Exists(_root));
    }

    [Fact]
    public void Two_workers_cannot_both_receive_permission_to_generate()
    {
        using var remote = new Remote();
        var first = Service(remote);
        var job = first.Create("owner", Request(), Authorized);
        var work = Assert.Single(first.PendingForWorker(20));
        OriginChapterWorkerAdmission? winner = null;
        remote.BeforeHeadPost = () => winner = Service(remote).AdmitForWorker(work.WorkId, job.SourceDigest, "one-execution");
        Assert.Throws<TeableRevisionConflictException>(() => first.AdmitForWorker(work.WorkId, job.SourceDigest, "one-execution"));
        Assert.NotNull(winner);
        Assert.True(winner.MayStartGeneration);
        Assert.False(Service(remote).AdmitForWorker(work.WorkId, job.SourceDigest, "one-execution").MayStartGeneration);
        Assert.Throws<InvalidOperationException>(() => Service(remote).AdmitForWorker(work.WorkId, job.SourceDigest, "different-execution"));
    }

    [Fact]
    public void Lost_dispatch_acknowledgement_never_replays_generation_on_new_host()
    {
        using var remote = new Remote();
        var service = Service(remote);
        var job = service.Create("owner", Request(), Authorized);
        var work = Assert.Single(service.PendingForWorker(20));
        remote.CommitThenFailHard = true;
        Assert.Throws<IOException>(() => service.AdmitForWorker(work.WorkId, job.SourceDigest, "execution"));
        int writes = remote.HeadPosts;
        var restored = Service(remote).AdmitForWorker(work.WorkId, job.SourceDigest, "execution");
        Assert.False(restored.MayStartGeneration);
        Assert.Equal(OriginChapterAuthoringStates.ReconciliationRequired, restored.Work.Job.State);
        Assert.Equal(writes, remote.HeadPosts);
    }

    [Fact]
    public void Competing_result_cannot_replace_committed_prose()
    {
        using var remote = new Remote();
        var service = Service(remote);
        var job = service.Create("owner", Request(), Authorized);
        var work = Assert.Single(service.PendingForWorker(20));
        service.AdmitForWorker(work.WorkId, job.SourceDigest, "execution");
        remote.BeforeHeadPost = () => Service(remote).CompleteForWorker(work.WorkId, job.SourceDigest,
            "execution", "Winner prose", new string('b', 64));
        Assert.Throws<TeableRevisionConflictException>(() => service.CompleteForWorker(work.WorkId, job.SourceDigest,
            "execution", "Different prose", new string('c', 64)));
        Assert.Equal("Winner prose", Service(remote).Get("owner", job.RequestId)!.DraftText);
        Assert.Throws<InvalidOperationException>(() => service.CompleteForWorker(work.WorkId, job.SourceDigest,
            "execution", "Different prose", new string('c', 64)));
    }

    [Fact]
    public void Interrupted_catalogue_registration_is_inert_and_can_resume_creation()
    {
        using var remote = new Remote();
        int checks = 0;
        Assert.Throws<UnauthorizedAccessException>(() => Service(remote).Create("owner", Request(), () => ++checks == 1));
        Assert.Empty(Service(remote).PendingForWorker(20));
        Assert.Null(Service(remote).Get("owner", Request().RequestId));
        var restored = Service(remote).Create("owner", Request(), Authorized);
        Assert.Equal(OriginChapterAuthoringStates.AwaitingAuthoring, restored.State);
        Assert.Single(Service(remote).PendingForWorker(20));
        Assert.False(Directory.Exists(_root));
    }

    [Fact]
    public void Concurrent_new_jobs_merge_only_after_explicit_reload_not_overwrite()
    {
        using var remote = new Remote();
        remote.BeforeHeadPost = () => Service(remote).Create("owner-b", Request(), Authorized);
        Assert.Throws<TeableRevisionConflictException>(() => Service(remote).Create("owner-a", Request(), Authorized));
        Assert.NotNull(Service(remote).Get("owner-b", Request().RequestId));
        Assert.Null(Service(remote).Get("owner-a", Request().RequestId));
        Service(remote).Create("owner-a", Request(), Authorized);
        Assert.Equal(2, Service(remote).PendingForWorker(20).Count);
    }

    [Fact]
    public void Remote_failures_never_read_a_legacy_local_job_or_create_a_local_shadow()
    {
        using var remote = new Remote();
        using var local = new OriginChapterAuthoringService(Configuration("local"));
        var localJob = local.Create("local-owner", Request(), Authorized);
        Assert.Null(Service(remote).Get("local-owner", localJob.RequestId));
        var remoteJob = Service(remote).Create("remote-owner", Request("remote"), Authorized);
        remote.FailReads = true;
        Assert.Throws<HttpRequestException>(() => Service(remote).Get("remote-owner", remoteJob.RequestId));
        Assert.Throws<HttpRequestException>(() => Service(remote).PendingForWorker(20));
        Assert.Single(Directory.GetFiles(Path.Combine(_root, "origin-chapter-jobs"), "*.json"));
        Assert.NotNull(local.Get("local-owner", localJob.RequestId));
    }

    [Fact]
    public async Task Invalid_primary_bytes_are_not_treated_as_a_missing_job()
    {
        using var remote = new Remote();
        var service = Service(remote);
        var job = service.Create("owner", Request(), Authorized);
        var work = Assert.Single(service.PendingForWorker(20));
        string stream = TeableOriginChapterStorage.JobStream(work.WorkId);
        var head = await remote.Store().ReadAsync(stream);
        await remote.Store().CompareExchangeAsync(stream, head, Guid.NewGuid(), "{}"u8.ToArray());
        int writes = remote.HeadPosts;
        Assert.Throws<InvalidDataException>(() => Service(remote).Get("owner", job.RequestId));
        Assert.Throws<InvalidDataException>(() => Service(remote).Create("owner", Request(), Authorized));
        Assert.Equal(writes, remote.HeadPosts);
    }

    [Fact]
    public async Task Invalid_catalogue_is_not_reset_and_owner_limit_includes_inert_reservations()
    {
        using var corrupt = new Remote();
        await corrupt.Store().CompareExchangeAsync(TeableOriginChapterStorage.CatalogueStream, null, Guid.NewGuid(), "{}"u8.ToArray());
        Assert.Throws<InvalidDataException>(() => Service(corrupt).PendingForWorker(20));

        using var remote = new Remote();
        string owner = Hash(JsonSerializer.Serialize("owner"));
        string requestHash = Hash(JsonSerializer.Serialize(Request().RequestId));
        var ids = Enumerable.Range(1, 127).Select(number => owner + "." + Hash("reserved-" + number))
            .Append(owner + "." + requestHash).ToArray();
        await remote.Store().CompareExchangeAsync(TeableOriginChapterStorage.CatalogueStream, null, Guid.NewGuid(),
            JsonSerializer.SerializeToUtf8Bytes(new { version = 1, workIds = ids }));
        // An existing reservation remains resumable even at the per-owner limit.
        Assert.NotNull(Service(remote).Create("owner", Request(), Authorized));
        Assert.Throws<InvalidOperationException>(() => Service(remote).Create("owner", Request("extra"), Authorized));
        Assert.NotNull(Service(remote).Create("different-owner", Request(), Authorized));
    }

    [Fact]
    public void Runtime_registration_selects_explicit_primary_mode_without_opening_a_local_store()
    {
        if (!OperatingSystem.IsLinux() || System.Runtime.InteropServices.RuntimeInformation.ProcessArchitecture != System.Runtime.InteropServices.Architecture.X64) return;
        Directory.CreateDirectory(_root, UnixFileMode.UserRead | UnixFileMode.UserWrite | UnixFileMode.UserExecute);
        string tokenFile = Path.Combine(_root, "synthetic-token");
        File.WriteAllText(tokenFile, "synthetic-teable-only");
        File.SetUnixFileMode(tokenFile, UnixFileMode.UserRead | UnixFileMode.UserWrite);
        var config = new ConfigurationBuilder().AddInMemoryCollection(new Dictionary<string, string?>
        {
            ["CHUMMER_ORIGIN_CHAPTER_STORAGE_PROVIDER"] = "teable",
            ["CHUMMER_TEABLE_ORIGIN"] = "https://teable.example/",
            ["CHUMMER_ORIGIN_TEABLE_TABLE_ID"] = "tbl1234567890123456",
            ["CHUMMER_ORIGIN_TEABLE_TOKEN_FILE"] = tokenFile
        }).Build();
        var services = new ServiceCollection();
        services.AddSingleton<IConfiguration>(config);
        services.AddHubAccountsAndCommunityContext();
        using var provider = services.BuildServiceProvider();
        Assert.True(provider.GetRequiredService<OriginChapterAuthoringService>().IsConfigured);
        Assert.Empty(Directory.GetDirectories(_root));
    }

    [Fact]
    public void Configuration_and_historical_erasure_do_not_claim_a_false_migration()
    {
        Assert.Throws<InvalidOperationException>(() => new OriginChapterAuthoringService(Configuration()));
        Assert.Throws<InvalidOperationException>(() => new OriginChapterAuthoringService(Configuration("unknown")));
        using var remote = new Remote();
        Assert.Throws<InvalidOperationException>(() => new OriginChapterAuthoringService(Configuration("local"), new(remote.Store())));
        var service = Service(remote);
        service.Create("owner", Request(), Authorized);
        int writes = remote.HeadPosts;
        Assert.Throws<InvalidOperationException>(() => service.EraseForSubject("owner"));
        Assert.Equal(writes, remote.HeadPosts);
        Assert.NotNull(Service(remote).Get("owner", Request().RequestId));
    }

    public void Dispose() { if (Directory.Exists(_root)) Directory.Delete(_root, true); }
}
