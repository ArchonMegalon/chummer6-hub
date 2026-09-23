using System.Text;
using Chummer.Run.Api.Services.Community;
using Chummer.Storage.Teable;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;
using Remote = Chummer.Tests.TeableRevisionStoreTests.Remote;

namespace Chummer.Tests;

public sealed class OriginPublicationTeablePersistenceTests : IDisposable
{
    private readonly string _root = Path.Combine(Path.GetTempPath(), "origin-publication-teable-" + Guid.NewGuid().ToString("N"));
    private static OriginDossierPublicationIndexEntry Entry(string project = "book") => new()
    {
        OwnerUserId = "synthetic-user", SubjectId = "synthetic-subject", ProjectId = project,
        Title = "Synthetic private book", RunnerAlias = "Runner", PublicationState = "draft"
    };
    private IConfiguration Configuration() => new ConfigurationBuilder().AddInMemoryCollection(
        new Dictionary<string, string?>
        {
            ["CHUMMER_ORIGIN_PUBLICATION_STORAGE_PROVIDER"] = "teable",
            ["CHUMMER_ORIGIN_DOSSIER_PUBLICATION_INDEX"] = Path.Combine(_root, "must-not-be-used.json")
        }).Build();
    private OriginDossierPublicationService Service(TeableOriginPublicationStorage store) =>
        new(Configuration(), null, null, NullLogger<OriginDossierPublicationService>.Instance, store);
    private string Stage(OriginDossierPublicationIndexEntry entry, string fileName = "book.md")
    {
        if (!OperatingSystem.IsLinux()) throw new PlatformNotSupportedException("Private staging tests require Linux.");
        string ownerRoot = Path.Combine(_root, TeableOriginPublicationStorage.Owner(entry));
        Directory.CreateDirectory(ownerRoot);
        File.SetUnixFileMode(ownerRoot, UnixFileMode.UserRead | UnixFileMode.UserWrite | UnixFileMode.UserExecute);
        string path = Path.Combine(ownerRoot, fileName);
        File.WriteAllText(path, "Synthetic private book bytes");
        File.SetUnixFileMode(path, UnixFileMode.UserRead | UnixFileMode.UserWrite);
        return path;
    }
    private OriginDossierPublicationIndexEntry Capture(TeableOriginPublicationStorage store)
    {
        var entry = Entry();
        return store.Capture(entry with { BookArtifactPath = Stage(entry) });
    }

    [Fact]
    public void Metadata_restores_without_local_index_and_does_not_promote_a_draft()
    {
        using var remote = new Remote();
        using (var writer = new TeableOriginPublicationStorage(remote.Store()))
        using (writer.Enter()) writer.Persist([Entry()]);
        using var cold = Service(new(remote.Store()));
        var restored = Assert.Single(cold.ListForAccount("synthetic-user", "synthetic-subject"));
        Assert.Equal("Synthetic private book", restored.Title);
        Assert.False(restored.GoldReady);
        Assert.Empty(cold.ListForAccount("other-user", "other-subject"));
        Assert.Null(cold.GetArtifactForAccount("other-user", "other-subject", "book", "book"));
        Assert.False(Directory.Exists(_root));
    }

    [Fact]
    public void Private_bytes_restore_without_staging_and_stream_keys_fit_the_transport_contract()
    {
        using var remote = new Remote();
        using (var writer = new TeableOriginPublicationStorage(remote.Store(), _root))
        using (writer.Enter()) writer.Persist([Capture(writer)]);
        Directory.Delete(_root, recursive: true);
        using var cold = new TeableOriginPublicationStorage(remote.Store());
        using (cold.Enter())
        {
            var restored = Assert.Single(cold.ReadEntries());
            Assert.StartsWith("teable-origin:", restored.BookArtifactPath);
            Assert.Equal("Synthetic private book bytes", Encoding.UTF8.GetString(cold.ReadBytes(restored.BookArtifactPath!)));
        }
        Assert.All(remote.Rows.Values, row => Assert.InRange(row["stream"]!.GetValue<string>().Length, 1, 128));
        Assert.False(Directory.Exists(_root));
    }

    [Fact]
    public void Nested_scope_keeps_outer_bytes_alive_until_outer_exit_then_clears_them()
    {
        using var remote = new Remote();
        using var store = new TeableOriginPublicationStorage(remote.Store(), _root);
        byte[] borrowed;
        using (store.Enter())
        {
            var saved = Capture(store);
            store.Persist([saved]);
            borrowed = store.ReadBytes(saved.BookArtifactPath!);
            using (store.Enter()) Assert.Equal("Synthetic private book bytes", Encoding.UTF8.GetString(borrowed));
            Assert.Equal("Synthetic private book bytes", Encoding.UTF8.GetString(borrowed));
        }
        Assert.All(borrowed, value => Assert.Equal((byte)0, value));
        Assert.Throws<InvalidOperationException>(() => store.ReadEntries());
    }

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public void References_cannot_be_transferred_to_another_owner_or_project(bool otherOwner)
    {
        using var remote = new Remote();
        using var store = new TeableOriginPublicationStorage(remote.Store(), _root);
        using (store.Enter())
        {
            var saved = Capture(store);
            var foreign = otherOwner ? saved with { OwnerUserId = "other-user" } : saved with { ProjectId = "other-book" };
            Assert.Throws<InvalidDataException>(() => store.Capture(foreign));
            Assert.Throws<InvalidDataException>(() => store.Persist([foreign]));
            Assert.Empty(store.ReadEntries());
        }
    }

    [Theory]
    [InlineData("missing")]
    [InlineData("corrupt")]
    [InlineData("outage")]
    public void Remote_bytes_fail_closed_even_if_the_original_local_file_still_exists(string failure)
    {
        using var remote = new Remote();
        using (var writer = new TeableOriginPublicationStorage(remote.Store(), _root))
        using (writer.Enter()) writer.Persist([Capture(writer)]);
        using var cold = new TeableOriginPublicationStorage(remote.Store());
        using (cold.Enter())
        {
            var entry = Assert.Single(cold.ReadEntries());
            var chunks = remote.Rows.Where(p => p.Value["stream"]!.GetValue<string>().StartsWith("origin-pub-asset-", StringComparison.Ordinal)).ToArray();
            if (failure == "missing") foreach (var chunk in chunks) remote.Rows.Remove(chunk.Key);
            else if (failure == "corrupt")
            {
                var head = chunks.First(p => p.Value["kind"]!.GetValue<string>() == "head").Value;
                var manifest = System.Text.Json.Nodes.JsonNode.Parse(head["payload"]!.GetValue<string>())!.AsObject();
                if (manifest["inlineBase64"] is not null)
                {
                    manifest["inlineBase64"] = "Y29ycnVwdA==";
                    head["payload"] = manifest.ToJsonString();
                }
                else chunks.First(p => p.Value["kind"]!.GetValue<string>() == "chunk").Value["payload"] = "Y29ycnVwdA==";
            }
            else remote.FailReads = true;
            if (failure == "outage") Assert.Throws<HttpRequestException>(() => cold.ReadBytes(entry.BookArtifactPath!));
            else Assert.Throws<InvalidDataException>(() => cold.ReadBytes(entry.BookArtifactPath!));
        }
    }

    [Theory]
    [InlineData("outside")]
    [InlineData("symlink")]
    [InlineData("permissions")]
    [InlineData("no-root")]
    public void Capture_rejects_untrusted_local_paths_before_remote_writes(string failure)
    {
        using var remote = new Remote();
        var entry = Entry();
        string path = Stage(entry);
        using var store = new TeableOriginPublicationStorage(remote.Store(), failure == "no-root" ? null : _root);
        if (failure == "outside") path = Stage(Entry("other-book"));
        else if (failure == "symlink")
        {
            string link = Path.Combine(Path.GetDirectoryName(path)!, "link.md");
            File.CreateSymbolicLink(link, path);
            path = link;
        }
        else if (failure == "permissions" && OperatingSystem.IsLinux()) File.SetUnixFileMode(path, UnixFileMode.UserRead | UnixFileMode.GroupRead);
        using (store.Enter())
        {
            if (failure == "permissions") Assert.Throws<UnauthorizedAccessException>(() => store.Capture(entry with { BookArtifactPath = path }));
            else if (failure == "symlink") Assert.Throws<IOException>(() => store.Capture(entry with { BookArtifactPath = path }));
            else Assert.Throws<InvalidDataException>(() => store.Capture(entry with { BookArtifactPath = path }));
        }
        Assert.Equal(0, remote.HeadPosts);
    }

    [Fact]
    public void Competing_index_writer_rejects_loser_and_preserves_the_winner()
    {
        using var remote = new Remote();
        using var first = new TeableOriginPublicationStorage(remote.Store());
        using var second = new TeableOriginPublicationStorage(remote.Store());
        using (first.Enter())
        {
            remote.BeforeHeadPost = () => { using (second.Enter()) second.Persist([Entry("winner")]); };
            Assert.Throws<TeableRevisionConflictException>(() => first.Persist([Entry("loser")]));
            Assert.Throws<InvalidOperationException>(() => first.ReadEntries());
        }
        using var cold = new TeableOriginPublicationStorage(remote.Store());
        using (cold.Enter()) Assert.Equal("winner", Assert.Single(cold.ReadEntries()).ProjectId);
    }

    [Fact]
    public void Lost_index_acknowledgement_restores_bytes_without_replaying_the_import()
    {
        using var remote = new Remote();
        using (var writer = new TeableOriginPublicationStorage(remote.Store(), _root))
        using (writer.Enter())
        {
            var entry = Capture(writer);
            remote.CommitThenFailHard = true;
            Assert.Throws<IOException>(() => writer.Persist([entry]));
        }
        int writes = remote.HeadPosts;
        using var cold = new TeableOriginPublicationStorage(remote.Store());
        using (cold.Enter())
        {
            var entry = Assert.Single(cold.ReadEntries());
            Assert.Equal("Synthetic private book bytes", Encoding.UTF8.GetString(cold.ReadBytes(entry.BookArtifactPath!)));
        }
        Assert.Equal(writes, remote.HeadPosts);
    }

    [Fact]
    public async Task Replacing_an_immutable_asset_revision_is_rejected()
    {
        using var remote = new Remote();
        using (var writer = new TeableOriginPublicationStorage(remote.Store(), _root))
        using (writer.Enter()) writer.Persist([Capture(writer)]);
        string stream = remote.Rows.Values.Select(row => row["stream"]!.GetValue<string>())
            .First(value => value.StartsWith("origin-pub-asset-", StringComparison.Ordinal));
        using var transport = remote.Store();
        var head = (await transport.ReadAsync(stream))!;
        await transport.CompareExchangeAsync(stream, head, Guid.NewGuid(), head.Bytes);
        using var cold = new TeableOriginPublicationStorage(remote.Store());
        using (cold.Enter()) Assert.Throws<InvalidDataException>(() => cold.ReadBytes(Assert.Single(cold.ReadEntries()).BookArtifactPath!));
    }

    [Fact]
    public void Account_erasure_and_missing_backend_fail_before_any_writes()
    {
        using var remote = new Remote();
        using var service = Service(new(remote.Store()));
        Assert.Throws<InvalidOperationException>(() => service.EnsureAccountErasureSupported());
        Assert.Throws<InvalidOperationException>(() => new OriginDossierPublicationService(Configuration(), NullLogger<OriginDossierPublicationService>.Instance));
        Assert.Equal(0, remote.HeadPosts);
        Assert.False(Directory.Exists(_root));
    }

    [Fact]
    public void Existing_reader_observes_current_ownership_and_rejects_outage_instead_of_using_cached_index()
    {
        using var remote = new Remote();
        using var writer = new TeableOriginPublicationStorage(remote.Store());
        using (writer.Enter()) writer.Persist([Entry()]);
        using var reader = Service(new(remote.Store()));
        Assert.Single(reader.ListForAccount("synthetic-user", "synthetic-subject"));
        using (writer.Enter()) writer.Persist([Entry() with { OwnerUserId = "other-user", SubjectId = "other-subject" }]);
        Assert.Empty(reader.ListForAccount("synthetic-user", "synthetic-subject"));
        Assert.Single(reader.ListForAccount("other-user", "other-subject"));
        remote.FailReads = true;
        Assert.Throws<HttpRequestException>(() => reader.ListForAccount("other-user", "other-subject"));
    }

    [Fact]
    public void Reference_with_trailing_newline_is_not_accepted_as_the_canonical_asset()
    {
        using var remote = new Remote();
        using var writer = new TeableOriginPublicationStorage(remote.Store(), _root);
        using (writer.Enter())
        {
            var entry = Capture(writer);
            Assert.Throws<InvalidDataException>(() => writer.Capture(entry with { BookArtifactPath = entry.BookArtifactPath + "\n" }));
        }
    }

    public void Dispose() { if (Directory.Exists(_root)) Directory.Delete(_root, recursive: true); }
}
