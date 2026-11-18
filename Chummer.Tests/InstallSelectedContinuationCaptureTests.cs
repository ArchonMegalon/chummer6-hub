using System.Text.Json;
using Chummer.Hub.Registry.Contracts.InstallLinking;
using Chummer.Run.Api.Services.InstallLinking;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.Configuration;
using Xunit;

namespace Chummer.Tests;

public sealed class InstallSelectedContinuationCaptureTests
{
    [Fact]
    public void Selected_full_continuation_is_detached_and_read_only_even_with_unrelated_corruption()
    {
        using var fixture = new Fixture();
        string original = fixture.Committed.WorkspaceContinuation!.Value.GetRawText();
        using var borrowedDocument = JsonDocument.Parse(original);
        fixture.Store.SnapshotsByKey[fixture.Key] = fixture.Committed with
        { WorkspaceContinuation = borrowedDocument.RootElement };
        fixture.Store.SnapshotsByKey[InstallLinkedWorkspaceSnapshotStore.ComposeKey(fixture.Committed.OwnerKey, "other")] =
            fixture.Committed with { WorkspaceId = "other", WorkspaceContinuationDigest = "invalid" };
        byte[] before = File.ReadAllBytes(fixture.Path);

        InstallLinkedWorkspaceSnapshotRecord captured = fixture.Capture();
        borrowedDocument.Dispose();

        Assert.NotSame(fixture.Committed, captured);
        Assert.Equal(original, captured.WorkspaceContinuation!.Value.GetRawText());
        Assert.Equal(fixture.Committed.WorkspaceContinuationDigest, captured.WorkspaceContinuationDigest);
        Assert.Equal(fixture.Committed.RemoteRevision, captured.RemoteRevision);
        Assert.Equal(fixture.Committed.ServerToken, captured.ServerToken);
        Assert.Equal(2, fixture.Store.SnapshotsByKey.Count);
        Assert.Equal(before, File.ReadAllBytes(fixture.Path));
    }

    [Theory]
    [InlineData("workspace-null")]
    [InlineData("workspace-padding")]
    [InlineData("workspace-trailing-padding")]
    [InlineData("workspace-control")]
    [InlineData("workspace-oversize")]
    [InlineData("workspace-surrogate")]
    [InlineData("subject-null")]
    [InlineData("subject-padding")]
    [InlineData("subject-oversize")]
    [InlineData("subject-surrogate")]
    [InlineData("revision-zero")]
    [InlineData("token-null")]
    [InlineData("token-prefix")]
    [InlineData("digest-truncated")]
    public void Invalid_selection_shape_never_reads_a_legacy_or_ambient_owner(string corruption)
    {
        using var fixture = new Fixture();
        ClaimedInstallationDto installation = fixture.Installation;
        string workspace = fixture.Committed.WorkspaceId;
        long revision = fixture.Committed.RemoteRevision;
        string token = fixture.Committed.ServerToken!;
        string digest = fixture.Committed.WorkspaceContinuationDigest!;
        switch (corruption)
        {
            case "workspace-null": workspace = null!; break;
            case "workspace-padding": workspace = " " + workspace; break;
            case "workspace-trailing-padding": workspace += " "; break;
            case "workspace-control": workspace += "\t"; break;
            case "workspace-oversize": workspace = new string('x', 129); break;
            case "workspace-surrogate": workspace = "\ud800"; break;
            case "subject-null": installation = installation with { SubjectId = null }; break;
            case "subject-padding": installation = installation with { SubjectId = " " + installation.SubjectId }; break;
            case "subject-oversize": installation = installation with { SubjectId = new string('é', 65) }; break;
            case "subject-surrogate": installation = installation with { SubjectId = "\ud800" }; break;
            case "revision-zero": revision = 0; break;
            case "token-null": token = null!; break;
            case "token-prefix": token = "sha256:" + token; break;
            case "digest-truncated": digest = digest[..63]; break;
        }
        byte[] before = File.ReadAllBytes(fixture.Path);
        Assert.Equal(StatusCodes.Status400BadRequest, Assert.Throws<InstallLinkingOperationException>(() =>
            fixture.Service.CaptureSelectedContinuation(installation, workspace, revision, token, digest)).StatusCode);
        Assert.Equal(before, File.ReadAllBytes(fixture.Path));
    }

    [Theory]
    [InlineData("workspace")]
    [InlineData("subject")]
    public void Exact_case_changes_do_not_select_another_partition(string field)
    {
        using var fixture = new Fixture();
        Assert.Equal(StatusCodes.Status404NotFound, Assert.Throws<InstallLinkingOperationException>(() =>
            fixture.Service.CaptureSelectedContinuation(
                field == "subject" ? fixture.Installation with { SubjectId = "subject.case" } : fixture.Installation,
                field == "workspace" ? fixture.Committed.WorkspaceId.ToUpperInvariant() : fixture.Committed.WorkspaceId,
                fixture.Committed.RemoteRevision, fixture.Committed.ServerToken!, fixture.Committed.WorkspaceContinuationDigest!)).StatusCode);
    }

    [Theory]
    [InlineData("revision")]
    [InlineData("token")]
    [InlineData("digest")]
    public void Every_reviewed_authority_component_must_still_match(string component)
    {
        using var fixture = new Fixture();
        Assert.Equal(StatusCodes.Status409Conflict, Assert.Throws<InstallLinkingOperationException>(() =>
            fixture.Service.CaptureSelectedContinuation(fixture.Installation, fixture.Committed.WorkspaceId,
                fixture.Committed.RemoteRevision + (component == "revision" ? 1 : 0),
                component == "token" ? ChangedDigest(fixture.Committed.ServerToken!) : fixture.Committed.ServerToken!,
                component == "digest" ? ChangedDigest(fixture.Committed.WorkspaceContinuationDigest!) : fixture.Committed.WorkspaceContinuationDigest!)).StatusCode);
    }

    [Theory]
    [InlineData("owner")]
    [InlineData("partial")]
    [InlineData("oversize")]
    [InlineData("stored-key")]
    public void Stored_full_continuation_is_revalidated_by_the_actual_core_codec(string corruption)
    {
        using var fixture = new Fixture();
        InstallLinkedWorkspaceSnapshotRecord changed = fixture.Committed;
        if (corruption == "owner")
        {
            var foreign = InstallLinkedWorkspaceSnapshotTransferTests.ToContinuationRecord(
                InstallLinkedWorkspaceSnapshotTransferTests.SampleContinuation("Other.Subject"));
            changed = changed with { WorkspaceContinuation = foreign.WorkspaceContinuation,
                WorkspaceContinuationDigest = foreign.WorkspaceContinuationDigest };
        }
        else if (corruption == "partial") changed = changed with { WorkspaceContinuation = null };
        else if (corruption == "stored-key") changed = changed with { OwnerKey = "subject:Other.Subject" };
        else changed = changed with { WorkspaceContinuation = JsonSerializer.SerializeToElement(new
            { payload = new string('x', InstallLinkedWorkspaceSnapshotTransfer.MaxSnapshotBytes + 1) }) };
        fixture.Store.SnapshotsByKey[fixture.Key] = changed;
        byte[] before = File.ReadAllBytes(fixture.Path);

        Assert.Equal(StatusCodes.Status503ServiceUnavailable, Assert.Throws<InstallLinkingOperationException>(() =>
            fixture.Service.CaptureSelectedContinuation(fixture.Installation, changed.WorkspaceId,
                changed.RemoteRevision, changed.ServerToken!, changed.WorkspaceContinuationDigest!)).StatusCode);
        Assert.Equal(before, File.ReadAllBytes(fixture.Path));
    }

    [Fact]
    public void Projection_only_row_cannot_satisfy_a_full_continuation_selection()
    {
        using var fixture = new Fixture();
        var projection = InstallLinkedWorkspaceSnapshotTransferTests.ToRecord(
            InstallLinkedWorkspaceSnapshotTransferTests.SampleSnapshot());
        fixture.Store.SnapshotsByKey[fixture.Key] = fixture.Committed with
        { WorkspaceContinuation = null, WorkspaceContinuationDigest = null,
            WorkspaceSnapshot = projection.WorkspaceSnapshot, WorkspaceSnapshotDigest = projection.WorkspaceSnapshotDigest };
        Assert.Equal(StatusCodes.Status409Conflict,
            Assert.Throws<InstallLinkingOperationException>(() => fixture.Capture()).StatusCode);
    }

    [Fact]
    public async Task Capture_waits_for_the_snapshot_writer_and_rejects_its_new_revision_with_identical_continuation()
    {
        using var fixture = new Fixture();
        using var started = new ManualResetEventSlim();
        Task<Exception?>? reader = null;
        try
        {
            lock (fixture.Store.Gate)
            {
                reader = Task.Run<Exception?>(() =>
                {
                    started.Set();
                    return Record.Exception(() => fixture.Capture());
                });
                Assert.True(started.Wait(TimeSpan.FromSeconds(5)));
                Assert.False(reader.IsCompleted);
                InstallLinkedWorkspaceSnapshotRecord advanced = fixture.Service.UpsertForInstallation(
                    fixture.Installation, fixture.Committed with { Name = "New display name" },
                    fixture.Committed.RemoteRevision, fixture.Committed.ServerToken);
                Assert.Equal(fixture.Committed.WorkspaceContinuationDigest, advanced.WorkspaceContinuationDigest);
                Assert.Equal(fixture.Committed.RemoteRevision + 1, advanced.RemoteRevision);
            }
            Exception? failure = await reader.WaitAsync(TimeSpan.FromSeconds(10));
            Assert.Equal(StatusCodes.Status409Conflict, Assert.IsType<InstallLinkingOperationException>(failure).StatusCode);
        }
        finally
        {
            // Drain even when an assertion fails; the fixture must outlive its reader.
            if (reader is not null)
                await reader.WaitAsync(TimeSpan.FromSeconds(10));
        }
    }

    private static string ChangedDigest(string digest) => (digest[0] == 'a' ? 'b' : 'a') + digest[1..];

    private sealed class Fixture : IDisposable
    {
        private readonly string _directory = System.IO.Path.Combine(System.IO.Path.GetTempPath(), "hub-selected-continuation-tests", Guid.NewGuid().ToString("N"));
        public Fixture()
        {
            Path = System.IO.Path.Combine(_directory, "snapshots.json");
            var configuration = new ConfigurationBuilder().AddInMemoryCollection(new Dictionary<string, string?>
            { ["CHUMMER_INSTALL_LINKED_WORKSPACE_SNAPSHOT_STORE_PATH"] = Path }).Build();
            Store = new InstallLinkedWorkspaceSnapshotStore(configuration);
            Service = new InstallLinkedWorkspaceSnapshotService(Store);
            // Isolated transport fixture only; live callers must supply the actual admitted store row.
            Installation = new("ins-transfer", "fixture", "internal", "fixture", "account_required", "active",
                DateTimeOffset.UtcNow, DateTimeOffset.UtcNow, UserId: "user", SubjectId: "Subject.Case");
            Committed = Service.UpsertForInstallation(Installation,
                InstallLinkedWorkspaceSnapshotTransferTests.ToContinuationRecord(
                    InstallLinkedWorkspaceSnapshotTransferTests.SampleContinuation(Installation.SubjectId!)), 0);
            Key = InstallLinkedWorkspaceSnapshotStore.ComposeKey(Committed.OwnerKey, Committed.WorkspaceId);
        }
        public string Path { get; }
        public string Key { get; }
        public InstallLinkedWorkspaceSnapshotStore Store { get; }
        public InstallLinkedWorkspaceSnapshotService Service { get; }
        public ClaimedInstallationDto Installation { get; }
        public InstallLinkedWorkspaceSnapshotRecord Committed { get; }
        public InstallLinkedWorkspaceSnapshotRecord Capture() => Service.CaptureSelectedContinuation(Installation,
            Committed.WorkspaceId, Committed.RemoteRevision, Committed.ServerToken!, Committed.WorkspaceContinuationDigest!);
        public void Dispose() { if (Directory.Exists(_directory)) Directory.Delete(_directory, recursive: true); }
    }
}
