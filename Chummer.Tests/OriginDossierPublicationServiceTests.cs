using System.Security.Cryptography;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.ViewModels;
using Chummer.Run.Contracts.Community;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using System.Text.Json;
using Xunit;

namespace Chummer.Tests;

public sealed class OriginDossierPublicationServiceTests
{
    [Fact]
    public void ListForAccountReturnsOnlyOwnedGoldReadyOriginDossierPublication()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), "chummer-origin-dossier-publications", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempRoot);
        string indexPath = Path.Combine(tempRoot, "origin-dossier-publications.json");
        OriginDossierArtifactPaths origin1 = CreateGoldArtifacts(tempRoot, "origin-1");
        OriginDossierArtifactPaths originStub = CreateGoldArtifacts(tempRoot, "origin-stub");
        File.WriteAllText(
            indexPath,
            JsonSerializer.Serialize(
                new
                {
                    publications = new object[]
                    {
                        BuildIndexEntry("user-1", "subject-1", "origin-1", "Glass Rain", "Vanta", origin1),
                        BuildIndexEntry("user-1", "subject-1", "origin-stub", "Stubbed Glass Rain", "Vanta", originStub),
                        new
                        {
                            ownerUserId = "other-user",
                            subjectId = "other-subject",
                            projectId = "origin-other",
                            title = "Other Runner",
                            runnerAlias = "Other",
                            publicationState = "published_for_owner",
                            chummerRunOwnerUrl = "https://chummer.run/account/work/origin-dossiers/origin-other",
                            audiobookshelfShareUrl = "https://audio.chummer.run/share/origin-other",
                            storySceneCoverUrl = "https://chummer.run/account/work/origin-dossiers/origin-other/cover",
                            providerAuthoredManuscriptImported = true,
                            undetectableHumanizerApplied = true,
                            storySceneCoverUsesSelectedCharacterFace = true,
                            audiobookshelfPlaybackVerified = true
                        }
                    }
                },
                new JsonSerializerOptions(JsonSerializerDefaults.Web) { WriteIndented = true }));

        var configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_ORIGIN_DOSSIER_PUBLICATION_INDEX"] = indexPath
            })
            .Build();

        var service = new OriginDossierPublicationService(
            configuration,
            NullLogger<OriginDossierPublicationService>.Instance);

        var publications = service.ListForAccount("user-1", "subject-1");

        Assert.Equal(2, publications.Count);
        Assert.Contains(publications, publication => publication.ProjectId == "origin-1" && publication.GoldReady);
        OriginDossierPublicationViewModel gold = publications.Single(publication => publication.ProjectId == "origin-1");
        Assert.Equal("origin.chummer.run/Varga/Mira/Vanta", gold.OriginEditionNamespace);
        Assert.Equal("https://chummer.run/account/work/origin-dossiers/origin-1/read", gold.AudiobookshelfDossierShareUrl);
        Assert.Equal("https://chummer.run/account/work/origin-dossiers/origin-1/listen", gold.AudiobookshelfShareUrl);
        Assert.Equal(
            "https://audio.chummer.run/share/origin-1-audiobook",
            service.GetAudiobookshelfShareForAccount("user-1", "subject-1", "origin-1", "listen"));
        Assert.Equal(
            "https://audio.chummer.run/share/origin-1-dossier",
            service.GetAudiobookshelfShareForAccount("user-1", "subject-1", "origin-1", "read"));
        Assert.Equal("origin-1", service.GetForAccount("user-1", "subject-1", "origin-1")?.ProjectId);
        Assert.Null(service.GetForAccount("user-1", "subject-1", "origin-other"));
        Assert.Contains(publications, publication =>
            publication.ProjectId == "origin-stub"
            && !publication.GoldReady
            && publication.MissingGoldRequirements.Contains("no generated placeholder artifact markers"));
        Assert.DoesNotContain(publications, publication => publication.ProjectId == "origin-other");

        OriginDossierPublicationArtifact? cover = service.GetArtifactForAccount("user-1", "subject-1", "origin-1", "cover");
        Assert.NotNull(cover);
        Assert.Equal(origin1.StorySceneCoverPath, cover.Path);
        Assert.Equal("image/png", cover.ContentType);
        Assert.Null(service.GetArtifactForAccount("other-user", "other-subject", "origin-1", "cover"));
        Assert.Null(service.GetArtifactForAccount("user-1", "subject-1", "origin-stub", "cover"));
    }

    [Fact]
    public void ListForAccountFailsClosedWhenPublicationIndexIsUnconfigured()
    {
        IConfiguration configuration = new ConfigurationBuilder().Build();
        var service = new OriginDossierPublicationService(
            configuration,
            NullLogger<OriginDossierPublicationService>.Instance);

        var publications = service.ListForAccount("user-1", "subject-1");

        Assert.Empty(publications);
    }

    [Fact]
    public void UpsertForAccountPersistsOwnedOriginDossierPublicationAndComputesOwnerUrl()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), "chummer-origin-dossier-publications", Guid.NewGuid().ToString("N"));
        string indexPath = Path.Combine(tempRoot, "origin-dossier-publications.json");
        var configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_ORIGIN_DOSSIER_PUBLICATION_INDEX"] = indexPath,
                ["CHUMMER_PUBLIC_BASE_URL"] = "https://chummer.run"
            })
            .Build();
        var service = new OriginDossierPublicationService(
            configuration,
            NullLogger<OriginDossierPublicationService>.Instance);
        var user = new Chummer.Run.Contracts.Community.HubUserDto(
            UserId: "user-1",
            SubjectId: "subject-1",
            DisplayName: "Runner Demo",
            Handle: "runner-demo",
            Visibility: "private",
            Timezone: "UTC",
            CountryCode: "AT",
            LinkedPrincipals: [],
            GroupIds: [],
            CreatedAtUtc: DateTimeOffset.UtcNow,
            UpdatedAtUtc: DateTimeOffset.UtcNow);
        OriginDossierArtifactPaths artifacts = CreateGoldArtifacts(tempRoot, "origin-imported");

        var imported = service.UpsertForAccount(
            user,
            "subject-1",
            new OriginDossierPublicationImportRequest(
                ProjectId: "origin-imported",
                Title: "Imported Rain",
                RunnerAlias: "Vanta",
                FamilyName: "Varga",
                GivenName: "Mira",
                RunnerName: "Vanta",
                OriginEditionNamespace: "origin.chummer.run/Varga/Mira/Vanta",
                PublicationState: "published_for_owner",
                BookArtifactUrl: "https://chummer.run/account/work/origin-dossiers/origin-imported/book",
                AudiobookshelfShareUrl: "https://audio.chummer.run/share/origin-imported-audiobook",
                AudiobookshelfDossierShareUrl: "https://audio.chummer.run/share/origin-imported-dossier",
                AudiobookshelfAudiobookShareUrl: "https://audio.chummer.run/share/origin-imported-audiobook",
                DossierVideoUrl: "https://chummer.run/account/work/origin-dossiers/origin-imported/video",
                StorySceneCoverUrl: "https://example.invalid/raw-origin-cover.png",
                ProviderAuthoredManuscriptImported: true,
                UndetectableHumanizerApplied: true,
                BookArtifactVerified: true,
                DossierVideoVerified: true,
                StorySceneCoverUsesSelectedCharacterFace: true,
                AudiobookshelfPlaybackVerified: true,
                TelegramShareDelivered: true,
                SourcePacketPath: artifacts.SourcePacketPath,
                SourcePacketReceiptPath: artifacts.SourcePacketReceiptPath,
                CanonAuditReceiptPath: artifacts.CanonAuditReceiptPath,
                ProviderManuscriptPath: artifacts.ProviderManuscriptPath,
                ProviderManuscriptReceiptPath: artifacts.ProviderManuscriptReceiptPath,
                HumanizerReceiptPath: artifacts.HumanizerReceiptPath,
                BookArtifactPath: artifacts.BookArtifactPath,
                BookArtifactReceiptPath: artifacts.BookArtifactReceiptPath,
                StorySceneCoverPath: artifacts.StorySceneCoverPath,
                StorySceneCoverReceiptPath: artifacts.StorySceneCoverReceiptPath,
                EbookArtifactPath: artifacts.EbookArtifactPath,
                EbookAudiobookshelfImportReceiptPath: artifacts.EbookAudiobookshelfImportReceiptPath,
                CoverConsistencyReceiptPath: artifacts.CoverConsistencyReceiptPath,
                AudiobookPath: artifacts.AudiobookPath,
                AudiobookshelfImportReceiptPath: artifacts.AudiobookshelfImportReceiptPath,
                DossierVideoPath: artifacts.DossierVideoPath,
                DossierVideoReceiptPath: artifacts.DossierVideoReceiptPath,
                MoviePosterPath: artifacts.StorySceneCoverPath,
                MovieSubtitlesPath: artifacts.MovieSubtitlesPath,
                MovieStoryboardPath: artifacts.MovieStoryboardPath,
                TelegramShareDeliveryReceiptPath: artifacts.TelegramShareDeliveryReceiptPath));

        Assert.True(imported.GoldReady);
        Assert.Equal("https://chummer.run/account/work/origin-dossiers/origin-imported", imported.ChummerRunOwnerUrl);
        Assert.Equal("https://chummer.run/account/work/origin-dossiers/origin-imported/book", imported.BookArtifactUrl);
        Assert.Equal("https://chummer.run/account/work/origin-dossiers/origin-imported/read", imported.AudiobookshelfDossierShareUrl);
        Assert.Equal("https://chummer.run/account/work/origin-dossiers/origin-imported/listen", imported.AudiobookshelfShareUrl);
        Assert.Equal("https://chummer.run/account/work/origin-dossiers/origin-imported/listen", imported.AudiobookshelfAudiobookShareUrl);
        Assert.Equal("https://chummer.run/account/work/origin-dossiers/origin-imported/cover", imported.StorySceneCoverUrl);
        Assert.Equal("https://chummer.run/account/work/origin-dossiers/origin-imported/video", imported.DossierVideoUrl);
        Assert.Equal(
            "https://audio.chummer.run/share/origin-imported-audiobook",
            service.GetAudiobookshelfShareForAccount("user-1", "subject-1", "origin-imported", "listen"));
        Assert.True(imported.TelegramShareDelivered);
        Assert.True(File.Exists(indexPath));
        OriginDossierPublicationViewModel? reloaded = service.GetForAccount("user-1", "subject-1", "origin-imported");
        Assert.NotNull(reloaded);
        Assert.True(reloaded.GoldReady);
    }

    [Fact]
    public void ListForAccountRequiresArchivedArtifactFilesAndJsonReceiptsBeforeGoldReady()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), "chummer-origin-dossier-publications", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempRoot);
        string indexPath = Path.Combine(tempRoot, "origin-dossier-publications.json");
        OriginDossierArtifactPaths artifacts = CreateGoldArtifacts(tempRoot, "origin-missing-archive");
        File.Delete(artifacts.AudiobookPath);
        File.WriteAllText(
            artifacts.TelegramShareDeliveryReceiptPath,
            "telegram receipt without json");
        File.WriteAllText(
            indexPath,
            JsonSerializer.Serialize(
                new { publications = new[] { BuildIndexEntry("user-1", "subject-1", "origin-missing-archive", "Broken Rain", "Vanta", artifacts) } },
                new JsonSerializerOptions(JsonSerializerDefaults.Web) { WriteIndented = true }));

        var configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_ORIGIN_DOSSIER_PUBLICATION_INDEX"] = indexPath
            })
            .Build();
        var service = new OriginDossierPublicationService(
            configuration,
            NullLogger<OriginDossierPublicationService>.Instance);

        OriginDossierPublicationViewModel publication = Assert.Single(service.ListForAccount("user-1", "subject-1"));

        Assert.False(publication.GoldReady);
        Assert.Contains("audiobook artifact path", publication.MissingGoldRequirements);
        Assert.Contains("Telegram share delivery receipt path", publication.MissingGoldRequirements);
    }

    [Fact]
    public void ListForAccountRequiresTrustedAudiobookshelfShareBeforeGoldReady()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), "chummer-origin-dossier-publications", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempRoot);
        string indexPath = Path.Combine(tempRoot, "origin-dossier-publications.json");
        OriginDossierArtifactPaths artifacts = CreateGoldArtifacts(tempRoot, "origin-untrusted-audio");
        object entry = BuildIndexEntry(
            "user-1",
            "subject-1",
            "origin-untrusted-audio",
            "Bad Share",
            "Vanta",
            artifacts,
            audiobookshelfShareUrl: "https://example.invalid/share/origin-untrusted-audio");
        File.WriteAllText(
            indexPath,
            JsonSerializer.Serialize(
                new { publications = new[] { entry } },
                new JsonSerializerOptions(JsonSerializerDefaults.Web) { WriteIndented = true }));

        var configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_ORIGIN_DOSSIER_PUBLICATION_INDEX"] = indexPath
            })
            .Build();
        var service = new OriginDossierPublicationService(
            configuration,
            NullLogger<OriginDossierPublicationService>.Instance);

        OriginDossierPublicationViewModel publication = Assert.Single(service.ListForAccount("user-1", "subject-1"));

        Assert.False(publication.GoldReady);
        Assert.Null(publication.AudiobookshelfShareUrl);
        Assert.Null(service.GetAudiobookshelfShareForAccount("user-1", "subject-1", "origin-untrusted-audio"));
        Assert.Contains("trusted Audiobookshelf share URL", publication.MissingGoldRequirements);
    }

    [Fact]
    public void ListForAccountRequiresOperationSpecificReceiptsBeforeGoldReady()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), "chummer-origin-dossier-publications", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempRoot);
        string indexPath = Path.Combine(tempRoot, "origin-dossier-publications.json");
        OriginDossierArtifactPaths artifacts = CreateGoldArtifacts(tempRoot, "origin-wrong-receipt");
        File.WriteAllText(
            artifacts.HumanizerReceiptPath,
            JsonSerializer.Serialize(
                new
                {
                    operation = "generic_json_receipt",
                    provider = "Some Other Provider",
                    status = "verified",
                    completedAtUtc = DateTimeOffset.UtcNow
                },
                new JsonSerializerOptions(JsonSerializerDefaults.Web) { WriteIndented = true }));
        File.WriteAllText(
            indexPath,
            JsonSerializer.Serialize(
                new { publications = new[] { BuildIndexEntry("user-1", "subject-1", "origin-wrong-receipt", "Wrong Receipt", "Vanta", artifacts) } },
                new JsonSerializerOptions(JsonSerializerDefaults.Web) { WriteIndented = true }));

        var configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_ORIGIN_DOSSIER_PUBLICATION_INDEX"] = indexPath
            })
            .Build();
        var service = new OriginDossierPublicationService(
            configuration,
            NullLogger<OriginDossierPublicationService>.Instance);

        OriginDossierPublicationViewModel publication = Assert.Single(service.ListForAccount("user-1", "subject-1"));

        Assert.False(publication.GoldReady);
        Assert.Contains("Undetectable Humanizer receipt path", publication.MissingGoldRequirements);
    }

    [Fact]
    public void ListForAccountRequiresExternalProviderReceiptsToCarryLiveProviderReferences()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), "chummer-origin-dossier-publications", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempRoot);
        string indexPath = Path.Combine(tempRoot, "origin-missing-live-provider-reference.json");
        OriginDossierArtifactPaths artifacts = CreateGoldArtifacts(tempRoot, "origin-missing-live-provider-reference");
        File.WriteAllText(
            artifacts.BookArtifactReceiptPath,
            JsonSerializer.Serialize(
                new
                {
                    operation = "book_artifact_import",
                    provider = "Inkfluence",
                    status = "verified",
                    completedAtUtc = DateTimeOffset.UtcNow,
                    artifactSha256 = new[] { ComputeSha256(artifacts.BookArtifactPath) }
                },
                new JsonSerializerOptions(JsonSerializerDefaults.Web) { WriteIndented = true }));
        File.WriteAllText(
            indexPath,
            JsonSerializer.Serialize(
                new { publications = new[] { BuildIndexEntry("user-1", "subject-1", "origin-missing-live-provider-reference", "Missing Live Reference", "Vanta", artifacts) } },
                new JsonSerializerOptions(JsonSerializerDefaults.Web) { WriteIndented = true }));

        var configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_ORIGIN_DOSSIER_PUBLICATION_INDEX"] = indexPath
            })
            .Build();
        var service = new OriginDossierPublicationService(
            configuration,
            NullLogger<OriginDossierPublicationService>.Instance);

        OriginDossierPublicationViewModel publication = Assert.Single(service.ListForAccount("user-1", "subject-1"));

        Assert.False(publication.GoldReady);
        Assert.Contains("book artifact receipt path", publication.MissingGoldRequirements);
        Assert.Null(service.GetArtifactForAccount("user-1", "subject-1", "origin-missing-live-provider-reference", "book"));
    }

    [Fact]
    public void ListForAccountRequiresProviderManuscriptReceiptFromApprovedProvider()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), "chummer-origin-dossier-publications", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempRoot);
        string indexPath = Path.Combine(tempRoot, "origin-internal-manuscript.json");
        OriginDossierArtifactPaths artifacts = CreateGoldArtifacts(tempRoot, "origin-internal-manuscript");
        File.WriteAllText(
            artifacts.ProviderManuscriptReceiptPath,
            JsonSerializer.Serialize(
                new
                {
                    operation = "provider_manuscript_import",
                    provider = "internal_chummer_generator",
                    status = "verified",
                    completedAtUtc = DateTimeOffset.UtcNow,
                    artifactSha256 = new[] { ComputeSha256(artifacts.ProviderManuscriptPath) }
                },
                new JsonSerializerOptions(JsonSerializerDefaults.Web) { WriteIndented = true }));
        File.WriteAllText(
            indexPath,
            JsonSerializer.Serialize(
                new { publications = new[] { BuildIndexEntry("user-1", "subject-1", "origin-internal-manuscript", "Internal Manuscript", "Vanta", artifacts) } },
                new JsonSerializerOptions(JsonSerializerDefaults.Web) { WriteIndented = true }));

        var configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_ORIGIN_DOSSIER_PUBLICATION_INDEX"] = indexPath
            })
            .Build();
        var service = new OriginDossierPublicationService(
            configuration,
            NullLogger<OriginDossierPublicationService>.Instance);

        OriginDossierPublicationViewModel publication = Assert.Single(service.ListForAccount("user-1", "subject-1"));

        Assert.False(publication.GoldReady);
        Assert.Contains("provider manuscript receipt path", publication.MissingGoldRequirements);
    }

    [Fact]
    public void ListForAccountRequiresApprovedSourcePacketWithExternalProcessingConsent()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), "chummer-origin-dossier-publications", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempRoot);
        string indexPath = Path.Combine(tempRoot, "origin-no-source-consent.json");
        OriginDossierArtifactPaths artifacts = CreateGoldArtifacts(tempRoot, "origin-no-source-consent");
        File.WriteAllText(
            artifacts.SourcePacketReceiptPath,
            JsonSerializer.Serialize(
                new
                {
                    operation = "origin_source_packet_approval",
                    provider = "Chummer",
                    status = "verified",
                    completedAtUtc = DateTimeOffset.UtcNow,
                    artifactSha256 = new[] { ComputeSha256(artifacts.SourcePacketPath) },
                    approval = "approved_source_packet"
                },
                new JsonSerializerOptions(JsonSerializerDefaults.Web) { WriteIndented = true }));
        File.WriteAllText(
            indexPath,
            JsonSerializer.Serialize(
                new { publications = new[] { BuildIndexEntry("user-1", "subject-1", "origin-no-source-consent", "No Source Consent", "Vanta", artifacts) } },
                new JsonSerializerOptions(JsonSerializerDefaults.Web) { WriteIndented = true }));

        var configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_ORIGIN_DOSSIER_PUBLICATION_INDEX"] = indexPath
            })
            .Build();
        var service = new OriginDossierPublicationService(
            configuration,
            NullLogger<OriginDossierPublicationService>.Instance);

        OriginDossierPublicationViewModel publication = Assert.Single(service.ListForAccount("user-1", "subject-1"));

        Assert.False(publication.GoldReady);
        Assert.Contains("approved source packet receipt path", publication.MissingGoldRequirements);
    }

    [Fact]
    public void ListForAccountRequiresPassingChummerCanonAuditBeforeGoldReady()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), "chummer-origin-dossier-publications", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempRoot);
        string indexPath = Path.Combine(tempRoot, "origin-canon-conflict.json");
        OriginDossierArtifactPaths artifacts = CreateGoldArtifacts(tempRoot, "origin-canon-conflict");
        File.WriteAllText(
            artifacts.CanonAuditReceiptPath,
            JsonSerializer.Serialize(
                new
                {
                    operation = "chummer_canon_audit",
                    provider = "Chummer",
                    status = "verified",
                    completedAtUtc = DateTimeOffset.UtcNow,
                    artifactSha256 = new[] { ComputeSha256(artifacts.SourcePacketPath), ComputeSha256(artifacts.ProviderManuscriptPath) },
                    audit = "canon_audit_failed hard_conflicts:1 privacy_findings:0"
                },
                new JsonSerializerOptions(JsonSerializerDefaults.Web) { WriteIndented = true }));
        File.WriteAllText(
            indexPath,
            JsonSerializer.Serialize(
                new { publications = new[] { BuildIndexEntry("user-1", "subject-1", "origin-canon-conflict", "Canon Conflict", "Vanta", artifacts) } },
                new JsonSerializerOptions(JsonSerializerDefaults.Web) { WriteIndented = true }));

        var configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_ORIGIN_DOSSIER_PUBLICATION_INDEX"] = indexPath
            })
            .Build();
        var service = new OriginDossierPublicationService(
            configuration,
            NullLogger<OriginDossierPublicationService>.Instance);

        OriginDossierPublicationViewModel publication = Assert.Single(service.ListForAccount("user-1", "subject-1"));

        Assert.False(publication.GoldReady);
        Assert.Contains("Chummer canon audit receipt path", publication.MissingGoldRequirements);
    }

    [Fact]
    public void ListForAccountRejectsArtifactReceiptsWhenArchivedBytesChange()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), "chummer-origin-dossier-publications", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempRoot);
        string indexPath = Path.Combine(tempRoot, "origin-tampered-book.json");
        OriginDossierArtifactPaths artifacts = CreateGoldArtifacts(tempRoot, "origin-tampered-book");
        File.AppendAllText(artifacts.BookArtifactPath, "\npost-receipt tamper");
        File.WriteAllText(
            indexPath,
            JsonSerializer.Serialize(
                new { publications = new[] { BuildIndexEntry("user-1", "subject-1", "origin-tampered-book", "Tampered Book", "Vanta", artifacts) } },
                new JsonSerializerOptions(JsonSerializerDefaults.Web) { WriteIndented = true }));

        var configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_ORIGIN_DOSSIER_PUBLICATION_INDEX"] = indexPath
            })
            .Build();
        var service = new OriginDossierPublicationService(
            configuration,
            NullLogger<OriginDossierPublicationService>.Instance);

        OriginDossierPublicationViewModel publication = Assert.Single(service.ListForAccount("user-1", "subject-1"));

        Assert.False(publication.GoldReady);
        Assert.Contains("book artifact receipt path", publication.MissingGoldRequirements);
        Assert.Null(service.GetArtifactForAccount("user-1", "subject-1", "origin-tampered-book", "book"));
    }

    [Fact]
    public void ListForAccountRequiresStorySceneCoverReceiptToProveSelectedCharacterFace()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), "chummer-origin-dossier-publications", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempRoot);
        string indexPath = Path.Combine(tempRoot, "origin-dossier-publications.json");
        OriginDossierArtifactPaths artifacts = CreateGoldArtifacts(tempRoot, "origin-generic-cover-face");
        File.WriteAllText(
            artifacts.StorySceneCoverReceiptPath,
            JsonSerializer.Serialize(
                new
                {
                    operation = "selected_face_scene_render",
                    provider = "rendered_cover_lane",
                    status = "verified",
                    completedAtUtc = DateTimeOffset.UtcNow,
                    deliveredLinks = new[]
                    {
                        "/account/work/origin-dossiers/origin-generic-cover-face",
                        "/account/work/origin-dossiers/origin-generic-cover-face/cover"
                    },
                    artifactSha256 = new[] { ComputeSha256(artifacts.StorySceneCoverPath) },
                    renderSummary = "Generated a generic cyberpunk rain scene with a shadowed face."
                },
                new JsonSerializerOptions(JsonSerializerDefaults.Web) { WriteIndented = true }));
        File.WriteAllText(
            indexPath,
            JsonSerializer.Serialize(
                new { publications = new[] { BuildIndexEntry("user-1", "subject-1", "origin-generic-cover-face", "Generic Cover", "Vanta", artifacts) } },
                new JsonSerializerOptions(JsonSerializerDefaults.Web) { WriteIndented = true }));

        var configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_ORIGIN_DOSSIER_PUBLICATION_INDEX"] = indexPath
            })
            .Build();
        var service = new OriginDossierPublicationService(
            configuration,
            NullLogger<OriginDossierPublicationService>.Instance);

        OriginDossierPublicationViewModel publication = Assert.Single(service.ListForAccount("user-1", "subject-1"));

        Assert.False(publication.GoldReady);
        Assert.Contains("story scene cover receipt path", publication.MissingGoldRequirements);
    }

    [Fact]
    public void ListForAccountRequiresAudiobookImportReceiptToProveApprovedVoiceProvider()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), "chummer-origin-dossier-publications", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempRoot);
        string indexPath = Path.Combine(tempRoot, "origin-edge-voice.json");
        OriginDossierArtifactPaths artifacts = CreateGoldArtifacts(tempRoot, "origin-edge-voice");
        File.WriteAllText(
            artifacts.AudiobookshelfImportReceiptPath,
            JsonSerializer.Serialize(
                new
                {
                    operation = "audiobookshelf_import",
                    provider = "Audiobookshelf",
                    status = "verified",
                    completedAtUtc = DateTimeOffset.UtcNow,
                    artifactSha256 = new[] { ComputeSha256(artifacts.AudiobookPath) },
                    narrationProvider = "edge_tts"
                },
                new JsonSerializerOptions(JsonSerializerDefaults.Web) { WriteIndented = true }));
        File.WriteAllText(
            indexPath,
            JsonSerializer.Serialize(
                new { publications = new[] { BuildIndexEntry("user-1", "subject-1", "origin-edge-voice", "Wrong Voice Provider", "Vanta", artifacts) } },
                new JsonSerializerOptions(JsonSerializerDefaults.Web) { WriteIndented = true }));

        var configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_ORIGIN_DOSSIER_PUBLICATION_INDEX"] = indexPath
            })
            .Build();
        var service = new OriginDossierPublicationService(
            configuration,
            NullLogger<OriginDossierPublicationService>.Instance);

        OriginDossierPublicationViewModel publication = Assert.Single(service.ListForAccount("user-1", "subject-1"));

        Assert.False(publication.GoldReady);
        Assert.Contains("Audiobookshelf import receipt path", publication.MissingGoldRequirements);
    }

    [Fact]
    public void ListForAccountRequiresTelegramReceiptToContainOwnerAndListenLinks()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), "chummer-origin-dossier-publications", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempRoot);
        string indexPath = Path.Combine(tempRoot, "origin-dossier-publications.json");
        OriginDossierArtifactPaths artifacts = CreateGoldArtifacts(tempRoot, "origin-wrong-telegram-link");
        File.WriteAllText(
            artifacts.TelegramShareDeliveryReceiptPath,
            JsonSerializer.Serialize(
                new
                {
                    operation = "telegram_share_delivery",
                    provider = "EA Telegram",
                    status = "delivered",
                    completedAtUtc = DateTimeOffset.UtcNow,
                    deliveredText = "Open a different dossier at https://chummer.run/account/work/origin-dossiers/other/listen"
                },
                new JsonSerializerOptions(JsonSerializerDefaults.Web) { WriteIndented = true }));
        File.WriteAllText(
            indexPath,
            JsonSerializer.Serialize(
                new { publications = new[] { BuildIndexEntry("user-1", "subject-1", "origin-wrong-telegram-link", "Wrong Telegram Link", "Vanta", artifacts) } },
                new JsonSerializerOptions(JsonSerializerDefaults.Web) { WriteIndented = true }));

        var configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_ORIGIN_DOSSIER_PUBLICATION_INDEX"] = indexPath
            })
            .Build();
        var service = new OriginDossierPublicationService(
            configuration,
            NullLogger<OriginDossierPublicationService>.Instance);

        OriginDossierPublicationViewModel publication = Assert.Single(service.ListForAccount("user-1", "subject-1"));

        Assert.False(publication.GoldReady);
        Assert.Contains("Telegram share delivery receipt path", publication.MissingGoldRequirements);
    }

    private static object BuildIndexEntry(
        string ownerUserId,
        string subjectId,
        string projectId,
        string title,
        string runnerAlias,
        OriginDossierArtifactPaths artifacts,
        string? audiobookshelfShareUrl = null)
        => new
        {
            ownerUserId,
            subjectId,
            projectId,
            title,
            runnerAlias,
            familyName = "Varga",
            givenName = "Mira",
            runnerName = runnerAlias,
            originEditionNamespace = $"origin.chummer.run/Varga/Mira/{runnerAlias}",
            publicationState = "published_for_owner",
            chummerRunOwnerUrl = $"https://chummer.run/account/work/origin-dossiers/{projectId}",
            bookArtifactUrl = $"https://chummer.run/account/work/origin-dossiers/{projectId}/book",
            audiobookshelfShareUrl = audiobookshelfShareUrl ?? $"https://audio.chummer.run/share/{projectId}-audiobook",
            audiobookshelfDossierShareUrl = $"https://audio.chummer.run/share/{projectId}-dossier",
            audiobookshelfAudiobookShareUrl = audiobookshelfShareUrl ?? $"https://audio.chummer.run/share/{projectId}-audiobook",
            dossierVideoUrl = $"https://chummer.run/account/work/origin-dossiers/{projectId}/video",
            storySceneCoverUrl = $"https://chummer.run/account/work/origin-dossiers/{projectId}/cover",
            providerAuthoredManuscriptImported = true,
            undetectableHumanizerApplied = true,
            bookArtifactVerified = true,
            dossierVideoVerified = true,
            storySceneCoverUsesSelectedCharacterFace = true,
            audiobookshelfPlaybackVerified = true,
            telegramShareDelivered = true,
            requiresAuthenticatedChummerRunUser = true,
            artifacts.SourcePacketPath,
            artifacts.SourcePacketReceiptPath,
            artifacts.CanonAuditReceiptPath,
            artifacts.ProviderManuscriptPath,
            artifacts.ProviderManuscriptReceiptPath,
            artifacts.HumanizerReceiptPath,
            artifacts.BookArtifactPath,
            artifacts.BookArtifactReceiptPath,
            artifacts.StorySceneCoverPath,
            artifacts.StorySceneCoverReceiptPath,
            artifacts.EbookArtifactPath,
            artifacts.EbookAudiobookshelfImportReceiptPath,
            artifacts.CoverConsistencyReceiptPath,
            artifacts.AudiobookPath,
            artifacts.AudiobookshelfImportReceiptPath,
            artifacts.DossierVideoPath,
            artifacts.DossierVideoReceiptPath,
            artifacts.MovieSubtitlesPath,
            artifacts.MovieStoryboardPath,
            artifacts.TelegramShareDeliveryReceiptPath
        };

    private static OriginDossierArtifactPaths CreateGoldArtifacts(string tempRoot, string projectId)
    {
        string projectRoot = Path.Combine(tempRoot, projectId);
        Directory.CreateDirectory(projectRoot);
        string sourcePacketPath = WriteArtifact(projectRoot, "approved-source-packet.json", """{"runnerAlias":"Vanta","approvedForExternalProcessing":true}""");
        string sourcePacketReceiptPath = WriteReceipt(
            projectRoot,
            "approved-source-packet.receipt.json",
            "origin_source_packet_approval",
            "Chummer",
            ["approved_source_packet", "external_processing_consent"],
            [sourcePacketPath]);
        string providerManuscriptPath = WriteArtifact(projectRoot, "provider-manuscript.md", "Provider-authored Origin Dossier manuscript.");
        string providerManuscriptReceiptPath = WriteReceipt(
            projectRoot,
            "provider-manuscript.receipt.json",
            "provider_manuscript_import",
            "Inkfluence",
            artifactPaths: [providerManuscriptPath]);
        string humanizerReceiptPath = WriteReceipt(
            projectRoot,
            "undetectable-humanizer.receipt.json",
            "undetectable_humanizer_postprocess",
            "Undetectable Humanizer",
            artifactPaths: [providerManuscriptPath]);
        string canonAuditReceiptPath = WriteReceipt(
            projectRoot,
            "chummer-canon-audit.receipt.json",
            "chummer_canon_audit",
            "Chummer",
            ["canon_audit_passed", "hard_conflicts:0", "privacy_findings:0"],
            [sourcePacketPath, providerManuscriptPath]);
        string bookArtifactPath = WriteArtifact(projectRoot, "book.pdf", "%PDF-1.7\nOrigin Dossier book artifact\n");
        string bookArtifactReceiptPath = WriteReceipt(
            projectRoot,
            "book.receipt.json",
            "book_artifact_import",
            "Inkfluence",
            artifactPaths: [bookArtifactPath]);
        string ebookArtifactPath = WriteArtifact(projectRoot, "ebook.epub", "EPUB Origin Dossier ebook artifact with embedded cover");
        string ebookAudiobookshelfImportReceiptPath = WriteReceipt(
            projectRoot,
            "audiobookshelf-dossier-import.receipt.json",
            "audiobookshelf_dossier_import",
            "Audiobookshelf",
            [$"dossierShare: https://audio.chummer.run/share/{projectId}-dossier"],
            artifactPaths: [ebookArtifactPath]);
        string storySceneCoverPath = WriteArtifact(projectRoot, "story-scene-cover.png", "PNG story scene cover artifact");
        string storySceneCoverReceiptPath = WriteReceipt(
            projectRoot,
            "story-scene-cover.receipt.json",
            "selected_face_scene_render",
            "rendered_cover_lane",
            [
                $"/account/work/origin-dossiers/{projectId}",
                $"/account/work/origin-dossiers/{projectId}/cover",
                "origin.chummer.run/Varga/Mira/Vanta",
                "selected_character_face"
            ],
            artifactPaths: [storySceneCoverPath]);
        string coverConsistencyReceiptPath = WriteReceipt(
            projectRoot,
            "cover-consistency.receipt.json",
            "origin_edition_cover_consistency",
            "Chummer",
            [
                ComputeSha256(storySceneCoverPath),
                "origin.chummer.run/Varga/Mira/Vanta",
                "ebook_cover_embedded",
                "m4b_cover_embedded",
                "movie_poster_matches_cover"
            ]);
        string audiobookPath = WriteArtifact(projectRoot, "audiobook.m4b", "M4B audiobook artifact");
        string audiobookshelfImportReceiptPath = WriteReceipt(
            projectRoot,
            "audiobookshelf-import.receipt.json",
            "audiobookshelf_import",
            "Audiobookshelf",
            ["narrationProvider: Unmixr"],
            artifactPaths: [audiobookPath]);
        string dossierVideoPath = WriteArtifact(projectRoot, "dossier-film.mp4", "MP4 dossier film artifact");
        string movieSubtitlesPath = WriteArtifact(projectRoot, "subtitles.vtt", "WEBVTT\n\n00:00.000 --> 00:02.000\nOrigin scene.\n");
        string movieStoryboardPath = WriteArtifact(projectRoot, "storyboard.json", """{"sceneId":"clinic-door-rain"}""");
        string dossierVideoReceiptPath = WriteReceipt(
            projectRoot,
            "dossier-film.receipt.json",
            "dossier_video_import",
            "video_lane",
            artifactPaths: [dossierVideoPath]);
        string telegramShareDeliveryReceiptPath = WriteReceipt(
            projectRoot,
            "telegram-share.receipt.json",
            "telegram_share_delivery",
            "EA Telegram",
            [
                $"/account/work/origin-dossiers/{projectId}",
                $"/account/work/origin-dossiers/{projectId}/read",
                $"/account/work/origin-dossiers/{projectId}/listen",
                $"/account/work/origin-dossiers/{projectId}/watch",
                "origin.chummer.run/Varga/Mira/Vanta"
            ]);

        return new OriginDossierArtifactPaths(
            sourcePacketPath,
            sourcePacketReceiptPath,
            canonAuditReceiptPath,
            providerManuscriptPath,
            providerManuscriptReceiptPath,
            humanizerReceiptPath,
            bookArtifactPath,
            bookArtifactReceiptPath,
            storySceneCoverPath,
            storySceneCoverReceiptPath,
            ebookArtifactPath,
            ebookAudiobookshelfImportReceiptPath,
            coverConsistencyReceiptPath,
            audiobookPath,
            audiobookshelfImportReceiptPath,
            dossierVideoPath,
            dossierVideoReceiptPath,
            movieSubtitlesPath,
            movieStoryboardPath,
            telegramShareDeliveryReceiptPath);
    }

    private static string WriteArtifact(string projectRoot, string fileName, string contents)
    {
        string path = Path.Combine(projectRoot, fileName);
        File.WriteAllText(path, contents);
        return path;
    }

    private static string WriteReceipt(
        string projectRoot,
        string fileName,
        string operation,
        string provider,
        IReadOnlyList<string>? deliveredLinks = null,
        IReadOnlyList<string>? artifactPaths = null)
    {
        string path = Path.Combine(projectRoot, fileName);
        List<string> receiptLinks = (deliveredLinks ?? Array.Empty<string>()).ToList();
        if (!string.Equals(provider, "Chummer", StringComparison.OrdinalIgnoreCase))
        {
            receiptLinks.Add("operator_verified_live_run");
            receiptLinks.Add($"provider_receipt_reference:{provider}:{operation}");
        }

        File.WriteAllText(
            path,
            JsonSerializer.Serialize(
                new
                {
                    operation,
                    provider,
                    status = "verified",
                    completedAtUtc = DateTimeOffset.UtcNow,
                    deliveredLinks = receiptLinks,
                    artifactSha256 = (artifactPaths ?? Array.Empty<string>())
                        .Select(ComputeSha256)
                        .ToArray()
                },
                new JsonSerializerOptions(JsonSerializerDefaults.Web) { WriteIndented = true }));
        return path;
    }

    private static string ComputeSha256(string path)
    {
        using FileStream stream = File.OpenRead(path);
        return Convert.ToHexString(SHA256.HashData(stream)).ToLowerInvariant();
    }

    private sealed record OriginDossierArtifactPaths(
        string SourcePacketPath,
        string SourcePacketReceiptPath,
        string CanonAuditReceiptPath,
        string ProviderManuscriptPath,
        string ProviderManuscriptReceiptPath,
        string HumanizerReceiptPath,
        string BookArtifactPath,
        string BookArtifactReceiptPath,
        string StorySceneCoverPath,
        string StorySceneCoverReceiptPath,
        string EbookArtifactPath,
        string EbookAudiobookshelfImportReceiptPath,
        string CoverConsistencyReceiptPath,
        string AudiobookPath,
        string AudiobookshelfImportReceiptPath,
        string DossierVideoPath,
        string DossierVideoReceiptPath,
        string MovieSubtitlesPath,
        string MovieStoryboardPath,
        string TelegramShareDeliveryReceiptPath);
}
