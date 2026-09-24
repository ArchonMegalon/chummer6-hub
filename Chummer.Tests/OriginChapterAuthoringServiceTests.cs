using Chummer.Run.Api.Services.Community;
using Chummer.Run.Contracts.Community;
using Microsoft.Extensions.Configuration;
using Xunit;

namespace Chummer.Tests;

public sealed class OriginChapterAuthoringServiceTests : IDisposable
{
    private readonly string _root = Path.Combine(Path.GetTempPath(), "origin-chapter-tests-" + Guid.NewGuid().ToString("N"));
    private OriginChapterAuthoringService Service() => new(new ConfigurationBuilder().AddInMemoryCollection(
        new Dictionary<string, string?> { ["CHUMMER_RUNTIME_STATE_ROOT"] = _root }).Build());
    private static OriginChapterAuthoringRequest Request() => new("request-one", new("workspace-one", "chapter-one",
        new string('a', 64), "decision-one", "de-AT", "Synthetic runner",
        [new("fact-one", "decision-one", "The player selected Renraku.")]), true);
    private static bool Authorized() => true;

    private (OriginChapterAuthoringJob Job, OriginChapterWorkerItem Work) Accepted()
    {
        using var service = Service();
        var job = service.Create("subject-a", Request(), Authorized);
        var work = Assert.Single(service.PendingForWorker(20));
        service.AdmitForWorker(work.WorkId, job.SourceDigest, "admission-one");
        service.CompleteForWorker(work.WorkId, job.SourceDigest, "admission-one", "Accepted scene.", new string('c', 64));
        string text = Convert.ToHexStringLower(System.Security.Cryptography.SHA256.HashData(System.Text.Encoding.UTF8.GetBytes("Accepted scene.")));
        job = service.AcceptReading("subject-a", job.RequestId, job.SourceDigest, new string('c', 64), text, true, Authorized);
        return (job, service.GetForWorker(work.WorkId));
    }

    private static OriginChapterAuthoringRequest Next(OriginChapterAuthoringJob old)
        => new("request-two", old.Source with { ChapterId = "chapter-two", AcceptedDecisionId = "decision-two",
            ChapterDigest = new string('d', 64), Facts = [.. old.Source.Facts,
                new("fact-two", "decision-two", "The player selected corporate schooling.")] }, true)
        { Previous = new(old.RequestId, old.SourceDigest, old.ProviderReceiptDigest!, old.ReaderAcceptedTextDigest!) };

    [Fact]
    public void Successor_retains_exact_accepted_predecessor_and_opaque_worker_edge_after_restart()
    {
        var (old, work) = Accepted();
        var request = Next(old);
        var next = Service().Create("subject-a", request, Authorized);
        var restored = Service().Get("subject-a", next.RequestId)!;
        Assert.Equal(request.Previous, restored.Previous);
        Assert.Equal(next.SourceDigest, restored.SourceDigest);
        Assert.Equal(request.Previous, Service().Create("subject-a", request, Authorized).Previous);
        var pending = Assert.Single(Service().PendingForWorker(20));
        Assert.Equal(work.WorkId, pending.PreviousWorkId);
        Assert.Equal(work.BookRef, pending.BookRef);
        Assert.NotEqual(work.WorkId, pending.WorkId);
        Service().AdmitForWorker(pending.WorkId, next.SourceDigest, "admission-two");
        var completed = Service().CompleteForWorker(pending.WorkId, next.SourceDigest, "admission-two", "Next scene.", new string('e', 64));
        Assert.Equal(work.WorkId, completed.PreviousWorkId);
        Assert.Equal(request.Previous, completed.Job.Previous);
        Assert.Null(completed.Job.ReaderAcceptedTextDigest);
        Assert.Equal(System.Text.Json.JsonSerializer.Serialize(old),
            System.Text.Json.JsonSerializer.Serialize(Service().Get("subject-a", old.RequestId)));
    }

    [Theory]
    [InlineData("owner")]
    [InlineData("missing")]
    [InlineData("source")]
    [InlineData("receipt")]
    [InlineData("text")]
    [InlineData("workspace")]
    [InlineData("locale")]
    [InlineData("name")]
    [InlineData("chapter")]
    [InlineData("decision")]
    [InlineData("history")]
    public void Invalid_predecessor_does_not_create_or_register_a_successor(string change)
    {
        var (old, _) = Accepted();
        var request = Next(old);
        string owner = change == "owner" ? "subject-b" : "subject-a";
        request = change switch
        {
            "missing" => request with { Previous = request.Previous! with { RequestId = "missing" } },
            "source" => request with { Previous = request.Previous! with { SourceDigest = new string('0', 64) } },
            "receipt" => request with { Previous = request.Previous! with { ProviderReceiptDigest = new string('0', 64) } },
            "text" => request with { Previous = request.Previous! with { TextDigest = new string('0', 64) } },
            "workspace" => request with { Source = request.Source with { WorkspaceId = "other" } },
            "locale" => request with { Source = request.Source with { Locale = "en" } },
            "name" => request with { Source = request.Source with { RunnerName = "Other" } },
            "chapter" => request with { Source = request.Source with { ChapterId = old.Source.ChapterId } },
            "decision" => request with { Source = request.Source with { AcceptedDecisionId = old.Source.AcceptedDecisionId } },
            "history" => request with { Source = request.Source with { Facts = request.Source.Facts.Skip(1).ToArray() } },
            _ => request
        };
        Assert.Throws<InvalidOperationException>(() => Service().Create(owner, request, Authorized));
        Assert.Null(Service().Get(owner, request.RequestId));
        Assert.Empty(Service().PendingForWorker(20));
    }

    [Fact]
    public void Unaccepted_previous_text_is_not_an_automatic_reader_confirmation()
    {
        using var service = Service();
        var old = service.Create("subject-a", Request(), Authorized);
        var work = Assert.Single(service.PendingForWorker(20));
        service.AdmitForWorker(work.WorkId, old.SourceDigest, "admission-one");
        old = service.CompleteForWorker(work.WorkId, old.SourceDigest, "admission-one", "Unaccepted scene.", new string('c', 64)).Job;
        var request = Next(old) with { Previous = new(old.RequestId, old.SourceDigest, old.ProviderReceiptDigest!, new string('b', 64)) };
        Assert.Throws<InvalidOperationException>(() => service.Create("subject-a", request, Authorized));
        Assert.Null(service.Get("subject-a", old.RequestId)!.ReaderAcceptedTextDigest);
        Assert.Null(service.Get("subject-a", request.RequestId));
    }

    [Fact]
    public void Immutable_request_cannot_drop_or_change_predecessor_and_revocation_blocks_new_write()
    {
        var (old, _) = Accepted();
        var request = Next(old);
        int checks = 0;
        Assert.Throws<UnauthorizedAccessException>(() => Service().Create("subject-a", request, () => ++checks == 1));
        Assert.Null(Service().Get("subject-a", request.RequestId));
        Service().Create("subject-a", request, Authorized);
        Assert.Throws<InvalidOperationException>(() => Service().Create("subject-a", request with { Previous = null }, Authorized));
        Assert.Throws<InvalidOperationException>(() => Service().Create("subject-a", request with
            { Previous = request.Previous! with { TextDigest = new string('f', 64) } }, Authorized));
        Assert.Throws<ArgumentException>(() => Service().Create("subject-a", request with
            { Previous = request.Previous! with { RequestId = request.RequestId } }, Authorized));
        Assert.Throws<ArgumentException>(() => Service().Create("subject-a", request with
            { Previous = request.Previous! with { SourceDigest = "invalid" } }, Authorized));
    }

    [Fact]
    public void Historical_job_bytes_without_predecessor_keep_their_original_checksum()
    {
        var request = Request();
        var job = Service().Create("subject-a", request, Authorized);
        var legacy = new { job.RequestId, job.SourceDigest, job.Source, job.State, job.Provider, job.DraftText,
            job.ProviderReceiptDigest, job.RequiresReaderReview, job.AffectsMechanics, job.PublicationAuthorized };
        var options = new System.Text.Json.JsonSerializerOptions(System.Text.Json.JsonSerializerDefaults.Web);
        string path = Assert.Single(Directory.GetFiles(Path.Combine(_root, "origin-chapter-jobs"), "*.json"));
        string owner = Path.GetFileName(path)[..64];
        byte[] data = System.Text.Json.JsonSerializer.SerializeToUtf8Bytes(legacy, options);
        string digest = Convert.ToHexStringLower(System.Security.Cryptography.SHA256.HashData(data));
        File.WriteAllBytes(path, System.Text.Json.JsonSerializer.SerializeToUtf8Bytes(new
            { Schema = "chummer.origin.chapter-job/v1", OwnerDigest = owner, Job = legacy, Digest = digest }, options));
        var restored = Service().Get("subject-a", request.RequestId)!;
        Assert.Null(restored.Previous);
        Assert.Null(Assert.Single(Service().PendingForWorker(20)).PreviousWorkId);
        Assert.Equal(job.SourceDigest, restored.SourceDigest);
    }

    [Fact]
    public void Same_request_survives_cold_read_and_changed_source_is_rejected()
    {
        var request = Request();
        var original = Service().Create("subject-a", request, Authorized);
        var replay = Service().Create("subject-a", request, Authorized);
        Assert.Equal(original.SourceDigest, replay.SourceDigest);
        Assert.Equal(OriginChapterAuthoringStates.AwaitingAuthoring, Service().Get("subject-a", request.RequestId)!.State);
        Assert.Null(Service().Get("subject-b", request.RequestId));
        Assert.Throws<InvalidOperationException>(() => Service().Create("subject-a",
            request with { Source = request.Source with { RunnerName = "changed" } }, Authorized));
    }

    [Fact]
    public void Dispatch_is_fenced_before_remote_work_and_never_reissued_after_restart()
    {
        var job = Service().Create("subject-a", Request(), Authorized);
        Assert.True(Service().TryFenceDispatch("subject-a", job.RequestId, job.SourceDigest));
        Assert.False(Service().TryFenceDispatch("subject-a", job.RequestId, job.SourceDigest));
        Assert.Equal(OriginChapterAuthoringStates.ReconciliationRequired, Service().Get("subject-a", job.RequestId)!.State);
        Assert.Throws<InvalidOperationException>(() => Service().TryFenceDispatch("subject-a", job.RequestId, new string('b', 64)));
        Assert.Throws<KeyNotFoundException>(() => Service().TryFenceDispatch("subject-b", job.RequestId, job.SourceDigest));
        var result = Service().Complete("subject-a", job.RequestId, job.SourceDigest, "Synthetic draft", new string('c', 64));
        Assert.Equal(OriginChapterAuthoringStates.ReviewRequired, result.State);
        Assert.Equal("Synthetic draft", Service().Get("subject-a", job.RequestId)!.DraftText);
        Assert.False(result.AffectsMechanics);
        Assert.False(result.PublicationAuthorized);
        Assert.True(result.RequiresReaderReview);
        Assert.Equal(result.SourceDigest, Service().Complete("subject-a", job.RequestId, job.SourceDigest,
            "Synthetic draft", new string('c', 64)).SourceDigest);
        Assert.Throws<InvalidOperationException>(() => Service().Complete("subject-a", job.RequestId, job.SourceDigest,
            "Other text", new string('c', 64)));
    }

    [Fact]
    public void Reader_acceptance_binds_exact_text_source_receipt_owner_and_survives_restart()
    {
        var service = Service();
        var job = service.Create("subject", Request(), Authorized);
        var work = Assert.Single(service.PendingForWorker(20));
        string receipt = new string('c', 64), text = "Exact private draft.";
        string digest = Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(System.Text.Encoding.UTF8.GetBytes(text))).ToLowerInvariant();
        Assert.Throws<InvalidOperationException>(() => service.AcceptReading("subject", job.RequestId, job.SourceDigest, receipt, digest, true, Authorized));
        service.AdmitForWorker(work.WorkId, job.SourceDigest, "admission");
        service.CompleteForWorker(work.WorkId, job.SourceDigest, "admission", text, receipt);
        Assert.Null(Service().Get("subject", job.RequestId)!.ReaderAcceptedTextDigest);
        Assert.Throws<ArgumentException>(() => service.AcceptReading("subject", job.RequestId, job.SourceDigest, receipt, digest, false, Authorized));
        Assert.Throws<UnauthorizedAccessException>(() => service.AcceptReading("subject", job.RequestId, job.SourceDigest, receipt, digest, true, () => false));
        Assert.Throws<KeyNotFoundException>(() => service.AcceptReading("other-owner", job.RequestId, job.SourceDigest, receipt, digest, true, Authorized));
        Assert.Throws<InvalidOperationException>(() => service.AcceptReading("subject", job.RequestId, new string('b', 64), receipt, digest, true, Authorized));
        Assert.Throws<InvalidOperationException>(() => service.AcceptReading("subject", job.RequestId, job.SourceDigest, new string('b', 64), digest, true, Authorized));
        Assert.Throws<InvalidOperationException>(() => service.AcceptReading("subject", job.RequestId, job.SourceDigest, receipt, new string('b', 64), true, Authorized));
        var accepted = service.AcceptReading("subject", job.RequestId, job.SourceDigest, receipt, digest, true, Authorized);
        Assert.Equal(digest, accepted.ReaderAcceptedTextDigest);
        Assert.Equal(digest, Service().AcceptReading("subject", job.RequestId, job.SourceDigest, receipt, digest, true, Authorized).ReaderAcceptedTextDigest);
        Assert.Equal(digest, Service().GetForWorker(work.WorkId).Job.ReaderAcceptedTextDigest);
        Assert.Equal(digest, Service().CompleteForWorker(work.WorkId, job.SourceDigest, "admission", text, receipt).Job.ReaderAcceptedTextDigest);
        Assert.False(accepted.AffectsMechanics);
        Assert.False(accepted.PublicationAuthorized);
        Service().EraseForSubject("subject");
        Assert.Throws<KeyNotFoundException>(() => Service().AcceptReading("subject", job.RequestId, job.SourceDigest, receipt, digest, true, Authorized));
    }

    [Fact]
    public void Consent_source_bounds_and_current_authorization_are_required_before_storage()
    {
        var request = Request();
        Assert.Throws<ArgumentException>(() => Service().Create("subject-a", request with { ExternalProcessingConsent = false }, Authorized));
        Assert.Throws<ArgumentException>(() => Service().Create("subject-a", request with { Source = request.Source with { Locale = "fr-FR" } }, Authorized));
        Assert.Throws<ArgumentException>(() => Service().Create("subject-a", request with { Source = request.Source with
            { Facts = [new("fact-one", "decision-one", new string('x', 2049))] } }, Authorized));
        Assert.Throws<UnauthorizedAccessException>(() => Service().Create("subject-a", request, () => false));
        Assert.Null(Service().Get("subject-a", request.RequestId));
        var job = Service().Create("subject-a", request, Authorized);
        Assert.Throws<InvalidOperationException>(() => Service().Complete("subject-a", job.RequestId, job.SourceDigest,
            "Undispatched draft", new string('c', 64)));
    }

    [Fact]
    public void Erasure_is_owner_scoped_and_prevents_late_result_recreation()
    {
        var a = Service().Create("subject-a", Request(), Authorized);
        string aPath = Directory.GetFiles(Path.Combine(_root, "origin-chapter-jobs"), "*.json").Single();
        string orphan = aPath + ".tmp-" + Guid.NewGuid().ToString("N");
        File.Copy(aPath, orphan);
        Service().Create("subject-b", Request(), Authorized);
        Assert.True(Service().TryFenceDispatch("subject-a", a.RequestId, a.SourceDigest));
        Assert.Equal(2, Service().EraseForSubject("subject-a"));
        Assert.False(File.Exists(orphan));
        Assert.Equal(0, Service().EraseForSubject("subject-a"));
        Assert.Null(Service().Get("subject-a", a.RequestId));
        Assert.NotNull(Service().Get("subject-b", a.RequestId));
        Assert.Throws<KeyNotFoundException>(() => Service().Complete("subject-a", a.RequestId, a.SourceDigest,
            "Late draft", new string('c', 64)));
    }

    [Fact]
    public void Invalid_stored_bytes_fail_closed_instead_of_creating_a_new_job()
    {
        Service().Create("subject-a", Request(), Authorized);
        string path = Directory.GetFiles(Path.Combine(_root, "origin-chapter-jobs"), "*.json").Single();
        File.WriteAllText(path, "{}");
        Assert.Throws<InvalidDataException>(() => Service().Get("subject-a", Request().RequestId));
        Assert.Throws<InvalidDataException>(() => Service().Create("subject-a", Request(), Authorized));
    }

    public void Dispose() { if (Directory.Exists(_root)) Directory.Delete(_root, true); }
}
