using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using Chummer.Run.Api.Controllers;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class OriginDossierFirstPartyDocumentServiceTests
{
    private static readonly JsonSerializerOptions CanonicalJsonOptions = new(JsonSerializerDefaults.Web)
    {
        WriteIndented = true
    };

    [Fact]
    public void PreviewIsDeterministicPrivateAndProviderFree()
    {
        using Fixture fixture = new();

        OriginDossierFirstPartyDocumentProjection first = fixture.Service.Preview(
            "user-owner",
            "subject-owner",
            "origin-001",
            ValidRequest());
        OriginDossierFirstPartyDocumentProjection second = fixture.Service.Preview(
            "user-owner",
            "subject-owner",
            "origin-001",
            ValidRequest() with { Inputs = ValidRequest().Inputs!.Reverse().ToArray() });

        Assert.Equal(first.RevisionId, second.RevisionId);
        Assert.Equal(first.MarkdownSha256, second.MarkdownSha256);
        Assert.Equal(first.JsonSha256, second.JsonSha256);
        Assert.Equal(first.ReceiptSha256, second.ReceiptSha256);
        Assert.Equal("preview", first.State);
        Assert.True(first.PrivateOwnerScoped);
        Assert.Equal("non_canon_private_draft", first.CanonStatus);
        Assert.Equal("not_requested", first.ProviderExecution);
        Assert.Equal(0, first.ProviderCalls);
        Assert.Equal(0, first.QuotaUnitsClaimed);
        Assert.Equal("blocked_by_existing_governance", first.PremiumMediaState);
        Assert.Equal("unchanged", first.ReleaseScope);
        Assert.Equal("configured_private_storage_root", first.StoragePosture);
        Assert.Contains("PRIVATE OWNER-SCOPED ARTIFACT", first.Markdown, StringComparison.Ordinal);
        Assert.DoesNotContain("user-owner", first.ReceiptJson, StringComparison.Ordinal);
        Assert.DoesNotContain("subject-owner", first.ReceiptJson, StringComparison.Ordinal);
        Assert.Equal(Sha256(first.Markdown), first.MarkdownSha256);
        Assert.Equal(Sha256(first.Json), first.JsonSha256);
        Assert.Equal(Sha256(first.ReceiptJson), first.ReceiptSha256);
        string metadataPath = Directory.GetFiles(fixture.Root, "metadata.json", SearchOption.AllDirectories).Single();
        using (JsonDocument receipt = JsonDocument.Parse(first.ReceiptJson))
        {
            Assert.Equal(
                "chummer.origin-dossier.first-party-receipt/v2",
                receipt.RootElement.GetProperty("contractName").GetString());
            Assert.Equal(
                Sha256(File.ReadAllText(metadataPath, Encoding.UTF8)),
                receipt.RootElement.GetProperty("metadataSha256").GetString());
        }
        if (!OperatingSystem.IsWindows())
        {
            string artifactPath = Directory.GetFiles(fixture.Root, "document.md", SearchOption.AllDirectories).Single();
            Assert.Equal(
                UnixFileMode.UserRead | UnixFileMode.UserWrite,
                File.GetUnixFileMode(artifactPath));
        }
    }

    [Fact]
    public void ExportIsAnIdempotentLifecycleStepWithImmutableArtifactDigests()
    {
        using Fixture fixture = new();
        OriginDossierFirstPartyDocumentProjection preview = fixture.Service.Preview(
            "user-owner",
            "subject-owner",
            "origin-002",
            ValidRequest());

        OriginDossierFirstPartyDocumentProjection first = fixture.Service.Export(
            "user-owner",
            "subject-owner",
            "origin-002",
            preview.RevisionId);
        OriginDossierFirstPartyDocumentProjection second = fixture.Service.Export(
            "user-owner",
            "subject-owner",
            "origin-002",
            preview.RevisionId);

        Assert.Equal("exported", first.State);
        Assert.Equal(first, second);
        Assert.Equal(preview.MarkdownSha256, first.MarkdownSha256);
        Assert.Equal(preview.JsonSha256, first.JsonSha256);
        Assert.NotEqual(preview.ReceiptSha256, first.ReceiptSha256);
        Assert.Contains(preview.ReceiptSha256, first.ReceiptJson, StringComparison.Ordinal);

        OriginDossierFirstPartyExportArtifact markdown = fixture.Service.GetExportArtifactForOwner(
            "user-owner",
            "subject-owner",
            "origin-002",
            preview.RevisionId,
            "markdown");
        Assert.Equal(first.Markdown, markdown.Content);
        Assert.Equal(first.MarkdownSha256, markdown.Sha256);
        Assert.Equal("text/markdown; charset=utf-8", markdown.ContentType);
    }

    [Fact]
    public void OwnerScopeRejectsCrossUserReadsAndExports()
    {
        using Fixture fixture = new();
        OriginDossierFirstPartyDocumentProjection preview = fixture.Service.Preview(
            "user-owner",
            "subject-owner",
            "origin-003",
            ValidRequest());

        Assert.Null(fixture.Service.GetForOwner(
            "user-other",
            "subject-other",
            "origin-003",
            preview.RevisionId));
        Assert.Throws<KeyNotFoundException>(() => fixture.Service.Export(
            "user-other",
            "subject-other",
            "origin-003",
            preview.RevisionId));
    }

    [Fact]
    public async Task ConcurrentIdenticalPreviewsConvergeOnOneRevision()
    {
        using Fixture fixture = new();

        OriginDossierFirstPartyDocumentProjection[] results = await Task.WhenAll(
            Enumerable.Range(0, 32)
                .Select(_ => Task.Run(() => fixture.Service.Preview(
                    "user-owner",
                    "subject-owner",
                    "origin-004",
                    ValidRequest()))));

        Assert.Single(results.Select(static result => result.RevisionId).Distinct(StringComparer.Ordinal));
        Assert.Single(results.Select(static result => result.ReceiptSha256).Distinct(StringComparer.Ordinal));
        Assert.Single(Directory.GetDirectories(fixture.Root, "odfp-*", SearchOption.AllDirectories));
        Assert.Empty(Directory.GetDirectories(fixture.Root, "*.tmp-*", SearchOption.AllDirectories));
    }

    [Fact]
    public void PreviewRejectsUnapprovedOrProviderInputsBeforeWriting()
    {
        using Fixture fixture = new();
        OriginDossierFirstPartyDocumentRequest request = ValidRequest();

        Assert.Throws<InvalidOperationException>(() => fixture.Service.Preview(
            "user-owner",
            "subject-owner",
            "origin-005",
            request with { OwnerApproved = false }));
        Assert.Throws<InvalidOperationException>(() => fixture.Service.Preview(
            "user-owner",
            "subject-owner",
            "origin-005",
            request with
            {
                Inputs =
                [
                    new("backstory", "Provider-authored prose", "provider", "external-001", true)
                ]
            }));
        Assert.False(Directory.Exists(fixture.Root));
    }

    [Fact]
    public void StoredArtifactTamperingFailsClosed()
    {
        using Fixture fixture = new();
        OriginDossierFirstPartyDocumentProjection preview = fixture.Service.Preview(
            "user-owner",
            "subject-owner",
            "origin-006",
            ValidRequest());
        string markdownPath = Directory.GetFiles(fixture.Root, "document.md", SearchOption.AllDirectories).Single();
        File.AppendAllText(markdownPath, "tampered", Encoding.UTF8);

        Assert.Throws<InvalidDataException>(() => fixture.Service.GetForOwner(
            "user-owner",
            "subject-owner",
            "origin-006",
            preview.RevisionId));
    }

    [Theory]
    [InlineData("title")]
    [InlineData("input")]
    [InlineData("storage")]
    [InlineData("digest")]
    public void MetadataFieldTamperingFailsClosedBeforeEveryReadPath(string field)
    {
        using Fixture fixture = new();
        OriginDossierFirstPartyDocumentProjection preview = fixture.Service.Preview(
            "user-owner",
            "subject-owner",
            "origin-metadata-tamper",
            ValidRequest());
        string metadataPath = Path.Combine(RevisionRoot(fixture, preview.RevisionId), "metadata.json");
        MutateStoredJson(metadataPath, metadata =>
        {
            switch (field)
            {
                case "title":
                    metadata["title"] = "A forged title";
                    break;
                case "input":
                    metadata["inputs"]!.AsArray()[0]!["value"] = "A forged first-party input.";
                    break;
                case "storage":
                    metadata["storagePosture"] = "forged_public_storage";
                    break;
                case "digest":
                    metadata["markdownSha256"] = new string('0', 64);
                    break;
                default:
                    throw new InvalidOperationException($"Unknown metadata tamper case '{field}'.");
            }
        });

        AssertEveryReadPathFailsClosed(fixture, "origin-metadata-tamper", preview.RevisionId);
    }

    [Theory]
    [InlineData("operation")]
    [InlineData("metadata-digest")]
    [InlineData("artifact-length")]
    public void PreviewReceiptTamperingFailsClosedBeforeEveryReadPath(string field)
    {
        using Fixture fixture = new();
        OriginDossierFirstPartyDocumentProjection preview = fixture.Service.Preview(
            "user-owner",
            "subject-owner",
            "origin-preview-receipt-tamper",
            ValidRequest());
        string receiptPath = Path.Combine(RevisionRoot(fixture, preview.RevisionId), "preview-receipt.json");
        MutateStoredJson(receiptPath, receipt =>
        {
            switch (field)
            {
                case "operation":
                    receipt["operation"] = "exported";
                    break;
                case "metadata-digest":
                    receipt["metadataSha256"] = new string('f', 64);
                    break;
                case "artifact-length":
                    receipt["artifacts"]!.AsArray()[0]!["utf16Length"] = 1;
                    break;
                default:
                    throw new InvalidOperationException($"Unknown preview receipt tamper case '{field}'.");
            }
        });

        AssertEveryReadPathFailsClosed(fixture, "origin-preview-receipt-tamper", preview.RevisionId);
    }

    [Theory]
    [InlineData("operation")]
    [InlineData("preview-digest")]
    [InlineData("artifact-digest")]
    public void ExportReceiptTamperingFailsClosedBeforeEveryReadPath(string field)
    {
        using Fixture fixture = new();
        OriginDossierFirstPartyDocumentProjection preview = fixture.Service.Preview(
            "user-owner",
            "subject-owner",
            "origin-export-receipt-tamper",
            ValidRequest());
        _ = fixture.Service.Export(
            "user-owner",
            "subject-owner",
            "origin-export-receipt-tamper",
            preview.RevisionId);
        string receiptPath = Path.Combine(RevisionRoot(fixture, preview.RevisionId), "export-receipt.json");
        MutateStoredJson(receiptPath, receipt =>
        {
            switch (field)
            {
                case "operation":
                    receipt["operation"] = "preview";
                    break;
                case "preview-digest":
                    receipt["previewReceiptSha256"] = new string('e', 64);
                    break;
                case "artifact-digest":
                    receipt["artifacts"]!.AsArray()[1]!["sha256"] = new string('d', 64);
                    break;
                default:
                    throw new InvalidOperationException($"Unknown export receipt tamper case '{field}'.");
            }
        });

        AssertEveryReadPathFailsClosed(fixture, "origin-export-receipt-tamper", preview.RevisionId);
    }

    [Fact]
    public void RevisionCapacityIsBoundedAndOwnerDeletionReleasesIt()
    {
        using Fixture fixture = new(maxPerOwner: 1, maxGlobal: 2);
        OriginDossierFirstPartyDocumentProjection first = fixture.Service.Preview(
            "user-owner",
            "subject-owner",
            "origin-capacity-one",
            ValidRequest());

        Assert.Throws<InvalidOperationException>(() => fixture.Service.Preview(
            "user-owner",
            "subject-owner",
            "origin-capacity-two",
            ValidRequest()));
        Assert.False(fixture.Service.DeleteForOwner(
            "user-other",
            "subject-other",
            "origin-capacity-one",
            first.RevisionId));
        Assert.True(fixture.Service.DeleteForOwner(
            "user-owner",
            "subject-owner",
            "origin-capacity-one",
            first.RevisionId));
        Assert.Null(fixture.Service.GetForOwner(
            "user-owner",
            "subject-owner",
            "origin-capacity-one",
            first.RevisionId));

        _ = fixture.Service.Preview(
            "user-owner",
            "subject-owner",
            "origin-capacity-two",
            ValidRequest());
        _ = fixture.Service.Preview(
            "user-second",
            "subject-second",
            "origin-capacity-three",
            ValidRequest());
        Assert.Throws<InvalidOperationException>(() => fixture.Service.Preview(
            "user-third",
            "subject-third",
            "origin-capacity-four",
            ValidRequest()));
    }

    [Fact]
    public void CorruptProjectionCanBeDeletedOnlyByItsDerivedOwnerScope()
    {
        using Fixture fixture = new();
        OriginDossierFirstPartyDocumentProjection preview = fixture.Service.Preview(
            "user-owner",
            "subject-owner",
            "origin-corrupt-delete",
            ValidRequest());
        string revisionRoot = RevisionRoot(fixture, preview.RevisionId);
        File.AppendAllText(Path.Combine(revisionRoot, "document.md"), "tampered", Encoding.UTF8);

        Assert.Throws<InvalidDataException>(() => fixture.Service.GetForOwner(
            "user-owner",
            "subject-owner",
            "origin-corrupt-delete",
            preview.RevisionId));
        Assert.False(fixture.Service.DeleteForOwner(
            "user-other",
            "subject-other",
            "origin-corrupt-delete",
            preview.RevisionId));
        Assert.True(Directory.Exists(revisionRoot));

        Assert.True(fixture.Service.DeleteForOwner(
            "user-owner",
            "subject-owner",
            "origin-corrupt-delete",
            preview.RevisionId));
        Assert.False(Directory.Exists(revisionRoot));
    }

    [Fact]
    public void OwnerDeletionFailsClosedBeforeFollowingLinkedStoredEntries()
    {
        if (OperatingSystem.IsWindows())
        {
            return;
        }

        using Fixture fixture = new();
        OriginDossierFirstPartyDocumentProjection preview = fixture.Service.Preview(
            "user-owner",
            "subject-owner",
            "origin-linked-delete",
            ValidRequest());
        string revisionRoot = RevisionRoot(fixture, preview.RevisionId);
        string externalRoot = Path.Combine(Path.GetTempPath(), "chummer-origin-linked-target", Guid.NewGuid().ToString("N"));
        string linkPath = Path.Combine(revisionRoot, "linked-private-data");
        Directory.CreateDirectory(externalRoot);
        string externalMarker = Path.Combine(externalRoot, "must-survive.txt");
        File.WriteAllText(externalMarker, "outside owner revision", Encoding.UTF8);
        Directory.CreateSymbolicLink(linkPath, externalRoot);
        try
        {
            Assert.Throws<InvalidDataException>(() => fixture.Service.DeleteForOwner(
                "user-owner",
                "subject-owner",
                "origin-linked-delete",
                preview.RevisionId));
            Assert.True(File.Exists(externalMarker));
            Assert.True(Directory.Exists(revisionRoot));
        }
        finally
        {
            if (Directory.Exists(linkPath))
            {
                Directory.Delete(linkPath);
            }

            if (Directory.Exists(externalRoot))
            {
                Directory.Delete(externalRoot, recursive: true);
            }
        }
    }

    [Fact]
    public void PreviewScavengesOnlyABoundedSetOfStaleInactiveCrashRemnants()
    {
        using Fixture fixture = new();
        OriginDossierFirstPartyDocumentProjection preview = fixture.Service.Preview(
            "user-owner",
            "subject-owner",
            "origin-temp-scavenge",
            ValidRequest());
        string projectRoot = Path.GetDirectoryName(RevisionRoot(fixture, preview.RevisionId))!;
        DateTime oldUtc = DateTime.UtcNow.AddHours(-4);
        string[] stale = Enumerable.Range(0, 18)
            .Select(_ => CreateTemporaryRevision(projectRoot, preview.RevisionId, oldUtc))
            .ToArray();
        string fresh = CreateTemporaryRevision(projectRoot, preview.RevisionId, DateTime.UtcNow);
        string active = CreateTemporaryRevision(projectRoot, preview.RevisionId, oldUtc, activeMarker: true);

        using (var activeLease = new FileStream(
                   Path.Combine(active, ".active"),
                   FileMode.Open,
                   FileAccess.ReadWrite,
                   FileShare.None))
        {
            _ = fixture.Service.Preview(
                "user-owner",
                "subject-owner",
                "origin-temp-scavenge",
                ValidRequest() with { Title = "The Rain Ledger — recovered" });

            Assert.Equal(2, stale.Count(Directory.Exists));
            Assert.True(Directory.Exists(fresh));
            Assert.True(Directory.Exists(active));
        }
    }

    [Fact]
    public void PreviewScavengerRejectsLinkedTempWithoutFollowingOrDeletingItsTarget()
    {
        if (OperatingSystem.IsWindows())
        {
            return;
        }

        using Fixture fixture = new();
        OriginDossierFirstPartyDocumentProjection preview = fixture.Service.Preview(
            "user-owner",
            "subject-owner",
            "origin-linked-temp",
            ValidRequest());
        string projectRoot = Path.GetDirectoryName(RevisionRoot(fixture, preview.RevisionId))!;
        string externalRoot = Path.Combine(Path.GetTempPath(), "chummer-origin-temp-link-target", Guid.NewGuid().ToString("N"));
        string externalMarker = Path.Combine(externalRoot, "must-survive.txt");
        string linkedTemp = Path.Combine(projectRoot, $"{preview.RevisionId}.tmp-{Guid.NewGuid():N}");
        Directory.CreateDirectory(externalRoot);
        File.WriteAllText(externalMarker, "outside temp root", Encoding.UTF8);
        Directory.CreateSymbolicLink(linkedTemp, externalRoot);
        try
        {
            Assert.Throws<InvalidDataException>(() => fixture.Service.Preview(
                "user-owner",
                "subject-owner",
                "origin-linked-temp",
                ValidRequest() with { Title = "The Rain Ledger — linked retry" }));
            Assert.True(File.Exists(externalMarker));
        }
        finally
        {
            if (Directory.Exists(linkedTemp))
            {
                Directory.Delete(linkedTemp);
            }

            if (Directory.Exists(externalRoot))
            {
                Directory.Delete(externalRoot, recursive: true);
            }
        }
    }

    [Fact]
    public async Task EveryPrivateJsonControllerResultCarriesCompleteNoStoreHeaders()
    {
        using Fixture fixture = new();
        Directory.CreateDirectory(fixture.Root);
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_COMMUNITY_STORE_PATH"] = Path.Combine(fixture.Root, "community-store.json"),
                ["CHUMMER_LOCAL_E2E_ACCESS_TOKEN"] = "origin-private-token",
                ["CHUMMER_LOCAL_E2E_SUBJECT_ID"] = "subject.origin.owner",
                ["CHUMMER_LOCAL_E2E_DISPLAY_NAME"] = "Origin Owner",
                ["CHUMMER_LOCAL_E2E_EMAIL"] = "origin-owner@example.invalid"
            })
            .Build();
        var store = new CommunityStore(configuration, NullLogger<CommunityStore>.Instance);
        var controller = new OriginDossierFirstPartyDocumentsController(
            new HubIdentityClient(new HttpClient(), configuration, NullLogger<HubIdentityClient>.Instance),
            new AccountService(store),
            fixture.Service)
        {
            ControllerContext = new ControllerContext { HttpContext = new DefaultHttpContext() }
        };
        controller.Request.Host = new HostString("localhost");
        controller.Request.Headers.Authorization = "Bearer origin-private-token";

        IActionResult invalidPreview = await controller.Preview(
            "origin-private-cache",
            request: null,
            CancellationToken.None);
        Assert.IsType<BadRequestObjectResult>(invalidPreview);
        AssertPrivateNoStoreHeaders(controller.Response.Headers);

        controller.Response.Headers.Clear();
        IActionResult previewResult = await controller.Preview(
            "origin-private-cache",
            ValidRequest(),
            CancellationToken.None);
        OriginDossierFirstPartyDocumentProjection preview = Assert.IsType<OriginDossierFirstPartyDocumentProjection>(
            Assert.IsType<OkObjectResult>(previewResult).Value);
        AssertPrivateNoStoreHeaders(controller.Response.Headers);

        controller.Response.Headers.Clear();
        Assert.IsType<OkObjectResult>(await controller.Get(
            "origin-private-cache",
            preview.RevisionId,
            CancellationToken.None));
        AssertPrivateNoStoreHeaders(controller.Response.Headers);

        controller.Response.Headers.Clear();
        Assert.IsType<OkObjectResult>(await controller.Export(
            "origin-private-cache",
            preview.RevisionId,
            CancellationToken.None));
        AssertPrivateNoStoreHeaders(controller.Response.Headers);

        controller.Response.Headers.Clear();
        Assert.IsType<NoContentResult>(await controller.Delete(
            "origin-private-cache",
            preview.RevisionId,
            CancellationToken.None));
        AssertPrivateNoStoreHeaders(controller.Response.Headers);
    }

    private static OriginDossierFirstPartyDocumentRequest ValidRequest()
        => new(
            "The Rain Ledger",
            "Mira Varga",
            [
                new("motivation", "Keep the clinic out of syndicate hands.", "character_sheet", "character-001", true),
                new("first run", "Recovered the clinic debt ledger during Session 4.", "campaign_record", "session-004", true),
                new("private note", "The safehouse key is still unaccounted for.", "player_note", "note-017", true)
            ],
            OwnerApproved: true);

    private static string Sha256(string value)
        => Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(value))).ToLowerInvariant();

    private static void MutateStoredJson(string path, Action<JsonObject> mutate)
    {
        JsonObject document = JsonNode.Parse(File.ReadAllText(path, Encoding.UTF8))?.AsObject()
            ?? throw new InvalidDataException($"Stored test document '{path}' is not a JSON object.");
        mutate(document);
        File.WriteAllText(
            path,
            document.ToJsonString(CanonicalJsonOptions).Replace("\r\n", "\n", StringComparison.Ordinal) + "\n",
            new UTF8Encoding(encoderShouldEmitUTF8Identifier: false));
    }

    private static void AssertEveryReadPathFailsClosed(
        Fixture fixture,
        string projectId,
        string revisionId)
    {
        Assert.Throws<InvalidDataException>(() => fixture.Service.GetForOwner(
            "user-owner",
            "subject-owner",
            projectId,
            revisionId));
        Assert.Throws<InvalidDataException>(() => fixture.Service.Export(
            "user-owner",
            "subject-owner",
            projectId,
            revisionId));
        Assert.Throws<InvalidDataException>(() => fixture.Service.GetExportArtifactForOwner(
            "user-owner",
            "subject-owner",
            projectId,
            revisionId,
            "receipt"));
    }

    private static string RevisionRoot(Fixture fixture, string revisionId)
        => Directory.GetDirectories(fixture.Root, revisionId, SearchOption.AllDirectories).Single();

    private static string CreateTemporaryRevision(
        string projectRoot,
        string revisionId,
        DateTime lastWriteUtc,
        bool activeMarker = false)
    {
        string temporaryRoot = Path.Combine(projectRoot, $"{revisionId}.tmp-{Guid.NewGuid():N}");
        Directory.CreateDirectory(temporaryRoot);
        if (activeMarker)
        {
            string activeMarkerPath = Path.Combine(temporaryRoot, ".active");
            File.WriteAllText(activeMarkerPath, string.Empty, Encoding.UTF8);
            File.SetLastWriteTimeUtc(activeMarkerPath, lastWriteUtc);
        }

        Directory.SetLastWriteTimeUtc(temporaryRoot, lastWriteUtc);
        return temporaryRoot;
    }

    private static void AssertPrivateNoStoreHeaders(IHeaderDictionary headers)
    {
        Assert.Equal("private, no-store, max-age=0", headers.CacheControl.ToString());
        Assert.Equal("no-store, max-age=0", headers["CDN-Cache-Control"].ToString());
        Assert.Equal("no-store, max-age=0", headers["Cloudflare-CDN-Cache-Control"].ToString());
        Assert.Equal("no-store", headers["Surrogate-Control"].ToString());
        Assert.Equal("no-cache", headers.Pragma.ToString());
        Assert.Equal("0", headers.Expires.ToString());
    }

    private sealed class Fixture : IDisposable
    {
        public Fixture(int? maxPerOwner = null, int? maxGlobal = null)
        {
            Root = Path.Combine(Path.GetTempPath(), "chummer-origin-first-party-tests", Guid.NewGuid().ToString("N"));
            var settings = new Dictionary<string, string?>
            {
                ["OriginDossier:FirstPartyDocumentRoot"] = Root
            };
            if (maxPerOwner is not null)
            {
                settings["OriginDossier:MaxFirstPartyRevisionsPerOwner"] = maxPerOwner.Value.ToString(System.Globalization.CultureInfo.InvariantCulture);
            }
            if (maxGlobal is not null)
            {
                settings["OriginDossier:MaxFirstPartyRevisionsGlobal"] = maxGlobal.Value.ToString(System.Globalization.CultureInfo.InvariantCulture);
            }
            IConfiguration configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(settings)
                .Build();
            Service = new OriginDossierFirstPartyDocumentService(configuration);
        }

        public string Root { get; }

        public OriginDossierFirstPartyDocumentService Service { get; }

        public void Dispose()
        {
            if (Directory.Exists(Root))
            {
                Directory.Delete(Root, recursive: true);
            }
        }
    }
}
