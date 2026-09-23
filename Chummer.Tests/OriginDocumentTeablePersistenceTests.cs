using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using Chummer.Run.Api;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.Services.Teable;
using Chummer.Storage.Teable;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Xunit;
using Remote = Chummer.Tests.TeableRevisionStoreTests.Remote;

namespace Chummer.Tests;

public sealed class OriginDocumentTeablePersistenceTests : IDisposable
{
    private readonly string _root = Path.Combine(Path.GetTempPath(), "origin-document-primary-" + Guid.NewGuid().ToString("N"));
    private IConfiguration Configuration(string mode = "teable", int ownerLimit = 64, int globalLimit = 2048)
        => new ConfigurationBuilder().AddInMemoryCollection(new Dictionary<string, string?>
        {
            ["CHUMMER_ORIGIN_DOCUMENT_STORAGE_PROVIDER"] = mode,
            ["CHUMMER_ORIGIN_DOSSIER_FIRST_PARTY_ROOT"] = _root,
            ["CHUMMER_ORIGIN_DOSSIER_FIRST_PARTY_MAX_REVISIONS_PER_OWNER"] = ownerLimit.ToString(),
            ["CHUMMER_ORIGIN_DOSSIER_FIRST_PARTY_MAX_REVISIONS_GLOBAL"] = globalLimit.ToString()
        }).Build();
    private OriginDossierFirstPartyDocumentService Service(Remote remote, int ownerLimit = 64, int globalLimit = 2048)
        => new(Configuration(ownerLimit: ownerLimit, globalLimit: globalLimit), new(remote.Store()));
    private static OriginDossierFirstPartyDocumentRequest Request(string title = "Synthetic origin")
        => new(title, "Synthetic runner", [new("school", "Selected a corporate school.", "player_note", "decision-one", true)], true);
    private static string Owner(string user = "owner", string subject = "subject")
        => Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes($"chummer-origin-dossier-owner-v1\0{user}\0{subject}")));

    [Fact]
    public void Cold_host_restores_exact_private_document_and_export_bytes_without_local_artifacts()
    {
        using var remote = new Remote();
        using var first = Service(remote);
        var preview = first.Preview("owner", "subject", "book", Request());
        Assert.Equal("teable_primary_private_storage", preview.StoragePosture);
        Assert.Equal("not_requested", preview.ProviderExecution);
        Assert.Equal(0, preview.ProviderCalls);
        Assert.Equal("non_canon_private_draft", preview.CanonStatus);
        using var cold = Service(remote);
        Assert.Equal(preview, cold.GetForOwner("owner", "subject", "book", preview.RevisionId));
        Assert.Throws<InvalidOperationException>(() => cold.GetExportArtifactForOwner("owner", "subject", "book", preview.RevisionId, "md"));
        var exported = cold.Export("owner", "subject", "book", preview.RevisionId);
        using var third = Service(remote);
        Assert.Equal(exported, third.GetForOwner("owner", "subject", "book", preview.RevisionId));
        int writes = remote.HeadPosts;
        Assert.Equal(exported, third.Export("owner", "subject", "book", preview.RevisionId));
        Assert.Equal(exported, third.Preview("owner", "subject", "book", Request()));
        foreach (string format in new[] { "markdown", "json", "receipt" })
        {
            var artifact = third.GetExportArtifactForOwner("owner", "subject", "book", preview.RevisionId, format);
            Assert.Equal(Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(artifact.Content))), artifact.Sha256);
        }
        Assert.Equal(writes, remote.HeadPosts);
        Assert.False(Directory.Exists(_root));
    }

    [Fact]
    public void Owner_subject_project_and_revision_remain_independent_scopes()
    {
        using var remote = new Remote();
        using var service = Service(remote);
        var preview = service.Preview("owner", "subject", "book", Request());
        Assert.Null(service.GetForOwner("other", "subject", "book", preview.RevisionId));
        Assert.Null(service.GetForOwner("owner", "other", "book", preview.RevisionId));
        Assert.Null(service.GetForOwner("owner", "subject", "other", preview.RevisionId));
        Assert.Null(service.GetForOwner("owner", "subject", "book", "another-revision"));
        Assert.Throws<KeyNotFoundException>(() => service.Export("other", "subject", "book", preview.RevisionId));
        Assert.Throws<ArgumentException>(() => service.GetForOwner("owner", "subject", "../book", preview.RevisionId));
        Assert.False(Directory.Exists(_root));
    }

    [Fact]
    public void Competing_catalogue_writers_do_not_drop_other_owners_or_exceed_capacity()
    {
        using var remote = new Remote();
        using var first = Service(remote, 1, 2);
        using var second = Service(remote, 1, 2);
        remote.BeforeHeadPost = () => second.Preview("other", "subject", "book", Request());
        Assert.Throws<TeableRevisionConflictException>(() => first.Preview("owner", "subject", "book", Request()));
        var admitted = first.Preview("owner", "subject", "book", Request());
        Assert.Equal(admitted, Service(remote, 1, 2).Preview("owner", "subject", "book", Request()));
        Assert.Throws<InvalidOperationException>(() => first.Preview("owner", "subject", "another", Request()));
        Assert.Throws<InvalidOperationException>(() => first.Preview("third", "subject", "book", Request()));
        Assert.Equal(4, remote.HeadPosts); // two catalogue commits and two document commits
    }

    [Fact]
    public void Inert_reservation_survives_lost_ack_without_hiding_a_document_or_bypassing_capacity()
    {
        using var remote = new Remote { CommitThenFailHard = true };
        using var service = Service(remote, 1, 1);
        Assert.Throws<IOException>(() => service.Preview("owner", "subject", "book", Request()));
        Assert.Throws<InvalidOperationException>(() => Service(remote, 1, 1).Preview("other", "subject", "book", Request()));
        var resumed = Service(remote, 1, 1).Preview("owner", "subject", "book", Request());
        Assert.Equal("preview", resumed.State);
        Assert.Equal(2, remote.HeadPosts);
    }

    [Fact]
    public void Competing_exports_fail_closed_then_converge_on_the_committed_receipt()
    {
        using var remote = new Remote();
        using var first = Service(remote);
        using var second = Service(remote);
        var preview = first.Preview("owner", "subject", "book", Request());
        OriginDossierFirstPartyDocumentProjection? winner = null;
        remote.BeforeHeadPost = () => winner = second.Export("owner", "subject", "book", preview.RevisionId);
        Assert.Throws<TeableRevisionConflictException>(() => first.Export("owner", "subject", "book", preview.RevisionId));
        Assert.Equal(winner, Service(remote).Export("owner", "subject", "book", preview.RevisionId));
        Assert.Equal(3, remote.HeadPosts);
    }

    [Fact]
    public void Lost_export_acknowledgement_restores_without_another_write()
    {
        using var remote = new Remote();
        using var service = Service(remote);
        var preview = service.Preview("owner", "subject", "book", Request());
        remote.CommitThenFailHard = true;
        Assert.Throws<IOException>(() => service.Export("owner", "subject", "book", preview.RevisionId));
        int writes = remote.HeadPosts;
        Assert.Equal("exported", Service(remote).Export("owner", "subject", "book", preview.RevisionId).State);
        Assert.Equal(writes, remote.HeadPosts);
    }

    [Theory]
    [InlineData("metadataJson")]
    [InlineData("markdown")]
    [InlineData("documentJson")]
    [InlineData("previewReceiptJson")]
    [InlineData("exportReceiptJson")]
    public async Task Hostile_remote_artifacts_are_rejected_by_the_same_semantic_validator(string field)
    {
        using var remote = new Remote();
        using var service = Service(remote);
        var preview = service.Preview("owner", "subject", "book", Request());
        string stream = TeableOriginDocumentStorage.DocumentStream(TeableOriginDocumentStorage.DocumentId(Owner(), "book", preview.RevisionId));
        var head = await remote.Store().ReadAsync(stream);
        var record = JsonNode.Parse(head!.Bytes)!;
        record["document"]![field] = "{}";
        await remote.Store().CompareExchangeAsync(stream, head, Guid.NewGuid(), JsonSerializer.SerializeToUtf8Bytes(record));
        int writes = remote.HeadPosts;
        Assert.Throws<InvalidDataException>(() => service.GetForOwner("owner", "subject", "book", preview.RevisionId));
        Assert.Throws<InvalidDataException>(() => service.Export("owner", "subject", "book", preview.RevisionId));
        Assert.Throws<InvalidDataException>(() => service.Preview("owner", "subject", "book", Request()));
        Assert.Equal(writes, remote.HeadPosts);
    }

    [Fact]
    public void Primary_outage_does_not_read_a_legacy_local_document_or_create_a_shadow()
    {
        using var remote = new Remote();
        using var local = new OriginDossierFirstPartyDocumentService(Configuration("local"));
        var original = local.Preview("owner", "subject", "book", Request());
        using var primary = Service(remote);
        Assert.Null(primary.GetForOwner("owner", "subject", "book", original.RevisionId));
        remote.FailReads = true;
        Assert.Throws<HttpRequestException>(() => primary.GetForOwner("owner", "subject", "book", original.RevisionId));
        Assert.Throws<HttpRequestException>(() => primary.Preview("owner", "subject", "book", Request()));
        Assert.Equal(original, local.GetForOwner("owner", "subject", "book", original.RevisionId));
        Assert.Single(Directory.GetDirectories(_root, "odfp-*", SearchOption.AllDirectories));
    }

    [Fact]
    public async Task Corrupt_catalogue_is_not_replaced_and_delete_does_not_claim_to_remove_private_history()
    {
        using var corrupt = new Remote();
        await corrupt.Store().CompareExchangeAsync(TeableOriginDocumentStorage.CatalogueStream, null, Guid.NewGuid(), "{}"u8.ToArray());
        Assert.Throws<InvalidDataException>(() => Service(corrupt).Preview("owner", "subject", "book", Request()));
        Assert.Equal(1, corrupt.HeadPosts);
        using var remote = new Remote();
        using var service = Service(remote);
        var preview = service.Preview("owner", "subject", "book", Request());
        int writes = remote.HeadPosts;
        Assert.Throws<InvalidOperationException>(() => service.DeleteForOwner("owner", "subject", "book", preview.RevisionId));
        Assert.Throws<InvalidOperationException>(service.EnsureAccountErasureSupported);
        Assert.Equal(writes, remote.HeadPosts);
        Assert.Equal(preview, Service(remote).GetForOwner("owner", "subject", "book", preview.RevisionId));
    }

    [Fact]
    public void Explicit_configuration_and_private_credential_registration_do_not_open_local_storage()
    {
        Assert.Throws<InvalidOperationException>(() => new OriginDossierFirstPartyDocumentService(Configuration()));
        Assert.Throws<InvalidOperationException>(() => new OriginDossierFirstPartyDocumentService(Configuration("unknown")));
        using var remote = new Remote();
        Assert.Throws<InvalidOperationException>(() => new OriginDossierFirstPartyDocumentService(Configuration("local"), new(remote.Store())));
        if (!OperatingSystem.IsLinux() || System.Runtime.InteropServices.RuntimeInformation.ProcessArchitecture != System.Runtime.InteropServices.Architecture.X64) return;
        Directory.CreateDirectory(_root, UnixFileMode.UserRead | UnixFileMode.UserWrite | UnixFileMode.UserExecute);
        string file = Path.Combine(_root, "synthetic-token");
        File.WriteAllText(file, "synthetic-teable-only");
        File.SetUnixFileMode(file, UnixFileMode.UserRead | UnixFileMode.UserWrite);
        var config = new ConfigurationBuilder().AddInMemoryCollection(new Dictionary<string, string?>
        {
            ["CHUMMER_ORIGIN_DOCUMENT_STORAGE_PROVIDER"] = "teable",
            ["CHUMMER_TEABLE_ORIGIN"] = "https://teable.example/",
            ["CHUMMER_ORIGIN_DOCUMENT_TEABLE_TABLE_ID"] = "tbl1234567890123456",
            ["CHUMMER_ORIGIN_DOCUMENT_TEABLE_TOKEN_FILE"] = file
        }).Build();
        var services = new ServiceCollection();
        services.AddSingleton<IConfiguration>(config);
        services.AddHubAccountsAndCommunityContext();
        using var provider = services.BuildServiceProvider();
        Assert.NotNull(provider.GetRequiredService<OriginDossierFirstPartyDocumentService>());
        Assert.Empty(Directory.GetDirectories(_root));
    }

    public void Dispose() { if (Directory.Exists(_root)) Directory.Delete(_root, recursive: true); }
}
