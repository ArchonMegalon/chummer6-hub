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
