using System.Security.Cryptography;
using System.Text;
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
    private const string OriginManuscriptAccountAlias = "INK01_ORIGIN";
    private const string OriginAudiobookAccountAlias = "UNMIXR_TIBOR_01";
    private const string OriginTelegramAccountAlias = "EA_TELEGRAM_ORIGIN";

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
        OriginDossierPublicationViewModel gold = publications.Single(publication => publication.ProjectId == "origin-1");
        Assert.True(gold.GoldReady, string.Join(", ", gold.MissingGoldRequirements));
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
                AudiobookshelfShareUrl: "https://audiobookshelf.girschele.com/audiobookshelf/share/origin-imported-audiobook",
                AudiobookshelfDossierShareUrl: "https://audiobookshelf.girschele.com/audiobookshelf/share/origin-imported-dossier",
                AudiobookshelfAudiobookShareUrl: "https://audiobookshelf.girschele.com/audiobookshelf/share/origin-imported-audiobook",
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
                MoviePosterPath: artifacts.MoviePosterPath,
                MovieSubtitlesPath: artifacts.MovieSubtitlesPath,
                MovieStoryboardPath: artifacts.MovieStoryboardPath,
                TelegramShareDeliveryReceiptPath: artifacts.TelegramShareDeliveryReceiptPath,
                FinalNoFallbackNoSentinelAuditReceiptPath: artifacts.FinalNoFallbackNoSentinelAuditReceiptPath));

        Assert.True(imported.GoldReady, string.Join(", ", imported.MissingGoldRequirements));
        Assert.Equal("https://chummer.run/account/work/origin-dossiers/origin-imported", imported.ChummerRunOwnerUrl);
        Assert.Equal("https://chummer.run/account/work/origin-dossiers/origin-imported/book", imported.BookArtifactUrl);
        Assert.Equal("https://chummer.run/account/work/origin-dossiers/origin-imported/read", imported.AudiobookshelfDossierShareUrl);
        Assert.Equal("https://chummer.run/account/work/origin-dossiers/origin-imported/listen", imported.AudiobookshelfShareUrl);
        Assert.Equal("https://chummer.run/account/work/origin-dossiers/origin-imported/listen", imported.AudiobookshelfAudiobookShareUrl);
        Assert.Equal("https://chummer.run/account/work/origin-dossiers/origin-imported/cover", imported.StorySceneCoverUrl);
        Assert.Equal("https://chummer.run/account/work/origin-dossiers/origin-imported/video", imported.DossierVideoUrl);
        Assert.Equal(
            "https://audiobookshelf.girschele.com/audiobookshelf/share/origin-imported-audiobook",
            service.GetAudiobookshelfShareForAccount("user-1", "subject-1", "origin-imported", "listen"));
        Assert.Equal(
            "https://audiobookshelf.girschele.com/audiobookshelf/share/origin-imported-dossier",
            service.GetAudiobookshelfShareForAccount("user-1", "subject-1", "origin-imported", "read"));
        Assert.True(imported.TelegramShareDelivered);
        Assert.True(File.Exists(indexPath));
        OriginDossierPublicationViewModel? reloaded = service.GetForAccount("user-1", "subject-1", "origin-imported");
        Assert.NotNull(reloaded);
        Assert.True(reloaded.GoldReady, string.Join(", ", reloaded.MissingGoldRequirements));
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
    public void ListForAccountRequiresConfiguredProviderAccountAliasesBeforeGoldReady()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), "chummer-origin-dossier-publications", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempRoot);
        string indexPath = Path.Combine(tempRoot, "origin-strict-account-alias.json");
        OriginDossierArtifactPaths artifacts = CreateGoldArtifacts(tempRoot, "origin-strict-account-alias");
        File.WriteAllText(
            indexPath,
            JsonSerializer.Serialize(
                new { publications = new[] { BuildIndexEntry("user-1", "subject-1", "origin-strict-account-alias", "Strict Alias", "Vanta", artifacts) } },
                new JsonSerializerOptions(JsonSerializerDefaults.Web) { WriteIndented = true }));

        var configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_ORIGIN_DOSSIER_PUBLICATION_INDEX"] = indexPath,
                ["CHUMMER_ORIGIN_MANUSCRIPT_ACCOUNT_ALIASES"] = "INK01_ORIGIN,YB02_CHUMMER_PRIVATE,FIRSTBOOK_PREMIUM",
                ["CHUMMER_ORIGIN_AUDIO_ACCOUNT_ALIASES"] = "UNMIXR_TIBOR_01,INK01_ORIGIN"
            })
            .Build();
        var service = new OriginDossierPublicationService(
            configuration,
            NullLogger<OriginDossierPublicationService>.Instance);

        OriginDossierPublicationViewModel publication = Assert.Single(service.ListForAccount("user-1", "subject-1"));

        Assert.True(publication.GoldReady, string.Join(", ", publication.MissingGoldRequirements));
    }

    [Fact]
    public void ListForAccountAcceptsProviderAccountAliasesFromRegistryWithoutDirectAliasEnv()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), "chummer-origin-dossier-publications", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempRoot);
        string indexPath = Path.Combine(tempRoot, "origin-registry-account-alias.json");
        OriginDossierArtifactPaths artifacts = CreateGoldArtifacts(tempRoot, "origin-registry-account-alias");
        File.WriteAllText(
            indexPath,
            JsonSerializer.Serialize(
                new { publications = new[] { BuildIndexEntry("user-1", "subject-1", "origin-registry-account-alias", "Registry Alias", "Vanta", artifacts) } },
                new JsonSerializerOptions(JsonSerializerDefaults.Web) { WriteIndented = true }));

        var configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_ORIGIN_DOSSIER_PUBLICATION_INDEX"] = indexPath,
                ["CHUMMER_ORIGIN_PROVIDER_ACCOUNT_REGISTRY"] = $$"""
                {
                  "accounts": [
                    {
                      "accountAlias": "{{OriginManuscriptAccountAlias}}",
                      "provider": "Inkfluence",
                      "status": "available",
                      "roles": ["manuscript", "origin"]
                    },
                    {
                      "accountAlias": "{{OriginAudiobookAccountAlias}}",
                      "provider": "Unmixr",
                      "status": "available",
                      "roles": ["audio", "audiobook", "origin"]
                    }
                  ]
                }
                """
            })
            .Build();
        var service = new OriginDossierPublicationService(
            configuration,
            NullLogger<OriginDossierPublicationService>.Instance);

        OriginDossierPublicationViewModel publication = Assert.Single(service.ListForAccount("user-1", "subject-1"));

        Assert.True(publication.GoldReady, string.Join(", ", publication.MissingGoldRequirements));
    }

    [Fact]
    public void ListForAccountAcceptsProviderAccountAliasesFromRegistryFilePath()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), "chummer-origin-dossier-publications", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempRoot);
        string indexPath = Path.Combine(tempRoot, "origin-registry-path-account-alias.json");
        string registryPath = Path.Combine(tempRoot, "ea-origin-provider-accounts.json");
        OriginDossierArtifactPaths artifacts = CreateGoldArtifacts(tempRoot, "origin-registry-path-account-alias");
        File.WriteAllText(
            registryPath,
            $$"""
            {
              "accounts": [
                {
                  "accountAlias": "{{OriginManuscriptAccountAlias}}",
                  "provider": "Inkfluence",
                  "status": "available",
                  "roles": ["manuscript", "origin"]
                },
                {
                  "accountAlias": "{{OriginAudiobookAccountAlias}}",
                  "provider": "Unmixr",
                  "status": "available",
                  "roles": ["audio", "audiobook", "origin"]
                }
              ]
            }
            """);
        File.WriteAllText(
            indexPath,
            JsonSerializer.Serialize(
                new { publications = new[] { BuildIndexEntry("user-1", "subject-1", "origin-registry-path-account-alias", "Registry Path Alias", "Vanta", artifacts) } },
                new JsonSerializerOptions(JsonSerializerDefaults.Web) { WriteIndented = true }));

        var configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_ORIGIN_DOSSIER_PUBLICATION_INDEX"] = indexPath,
                ["CHUMMER_ORIGIN_PROVIDER_ACCOUNT_REGISTRY_PATH"] = registryPath
            })
            .Build();
        var service = new OriginDossierPublicationService(
            configuration,
            NullLogger<OriginDossierPublicationService>.Instance);

        OriginDossierPublicationViewModel publication = Assert.Single(service.ListForAccount("user-1", "subject-1"));

        Assert.True(publication.GoldReady, string.Join(", ", publication.MissingGoldRequirements));
    }

    [Fact]
    public void ListForAccountFailsClosedWhenProviderAccountRegistryFileIsMalformed()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), "chummer-origin-dossier-publications", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempRoot);
        string indexPath = Path.Combine(tempRoot, "origin-malformed-registry-account-alias.json");
        string registryPath = Path.Combine(tempRoot, "ea-origin-provider-accounts.json");
        OriginDossierArtifactPaths artifacts = CreateGoldArtifacts(tempRoot, "origin-malformed-registry-account-alias");
        File.WriteAllText(registryPath, "{ this is not provider account registry json");
        File.WriteAllText(
            indexPath,
            JsonSerializer.Serialize(
                new { publications = new[] { BuildIndexEntry("user-1", "subject-1", "origin-malformed-registry-account-alias", "Malformed Registry Alias", "Vanta", artifacts) } },
                new JsonSerializerOptions(JsonSerializerDefaults.Web) { WriteIndented = true }));

        var configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_ORIGIN_DOSSIER_PUBLICATION_INDEX"] = indexPath,
                ["CHUMMER_ORIGIN_PROVIDER_ACCOUNT_REGISTRY_PATH"] = registryPath
            })
            .Build();
        var service = new OriginDossierPublicationService(
            configuration,
            NullLogger<OriginDossierPublicationService>.Instance);

        OriginDossierPublicationViewModel publication = Assert.Single(service.ListForAccount("user-1", "subject-1"));

        Assert.False(publication.GoldReady);
        Assert.Contains("provider manuscript account alias", publication.MissingGoldRequirements);
        Assert.Contains("audiobook provider account alias", publication.MissingGoldRequirements);
        Assert.Contains("trusted Audiobookshelf share URL", publication.MissingGoldRequirements);
        Assert.Contains("Telegram share delivery receipt path", publication.MissingGoldRequirements);
    }

    [Fact]
    public void ListForAccountFailsClosedWhenRegistryOnlyAccountsAreDisabled()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), "chummer-origin-dossier-publications", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempRoot);
        string indexPath = Path.Combine(tempRoot, "origin-disabled-registry-account-alias.json");
        OriginDossierArtifactPaths artifacts = CreateGoldArtifacts(tempRoot, "origin-disabled-registry-account-alias");
        File.WriteAllText(
            indexPath,
            JsonSerializer.Serialize(
                new { publications = new[] { BuildIndexEntry("user-1", "subject-1", "origin-disabled-registry-account-alias", "Disabled Registry Alias", "Vanta", artifacts) } },
                new JsonSerializerOptions(JsonSerializerDefaults.Web) { WriteIndented = true }));

        var configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_ORIGIN_DOSSIER_PUBLICATION_INDEX"] = indexPath,
                ["CHUMMER_ORIGIN_PROVIDER_ACCOUNT_REGISTRY"] = $$"""
                {
                  "accounts": [
                    {
                      "accountAlias": "{{OriginManuscriptAccountAlias}}",
                      "provider": "Inkfluence",
                      "status": "disabled",
                      "roles": ["manuscript", "origin"]
                    },
                    {
                      "accountAlias": "{{OriginAudiobookAccountAlias}}",
                      "provider": "Unmixr",
                      "status": "disabled",
                      "roles": ["audio", "audiobook", "origin"]
                    }
                  ]
                }
                """
            })
            .Build();
        var service = new OriginDossierPublicationService(
            configuration,
            NullLogger<OriginDossierPublicationService>.Instance);

        OriginDossierPublicationViewModel publication = Assert.Single(service.ListForAccount("user-1", "subject-1"));

        Assert.False(publication.GoldReady);
        Assert.Contains("provider manuscript account alias", publication.MissingGoldRequirements);
        Assert.Contains("audiobook provider account alias", publication.MissingGoldRequirements);
    }

    [Fact]
    public void ListForAccountAcceptsAudiobookshelfShareHostFromRegistry()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), "chummer-origin-dossier-publications", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempRoot);
        string indexPath = Path.Combine(tempRoot, "origin-registry-shelf-host.json");
        OriginDossierArtifactPaths artifacts = CreateGoldArtifacts(tempRoot, "origin-registry-shelf-host");
        File.WriteAllText(
            indexPath,
            JsonSerializer.Serialize(
                new
                {
                    publications = new[]
                    {
                        BuildIndexEntry(
                            "user-1",
                            "subject-1",
                            "origin-registry-shelf-host",
                            "Registry Shelf",
                            "Vanta",
                            artifacts,
                            audiobookshelfHost: "origin-shelf.example.invalid")
                    }
                },
                new JsonSerializerOptions(JsonSerializerDefaults.Web) { WriteIndented = true }));

        var configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_ORIGIN_DOSSIER_PUBLICATION_INDEX"] = indexPath,
                ["CHUMMER_ORIGIN_PROVIDER_ACCOUNT_REGISTRY"] = """
                {
                  "accounts": [
                    {
                      "accountAlias": "ABS_ORIGIN_01",
                      "provider": "Audiobookshelf",
                      "status": "available",
                      "roles": ["audiobookshelf", "book_share"],
                      "shareHost": "origin-shelf.example.invalid"
                    }
                  ]
                }
                """
            })
            .Build();
        var service = new OriginDossierPublicationService(
            configuration,
            NullLogger<OriginDossierPublicationService>.Instance);

        OriginDossierPublicationViewModel publication = Assert.Single(service.ListForAccount("user-1", "subject-1"));

        Assert.True(publication.GoldReady, string.Join(", ", publication.MissingGoldRequirements));
        Assert.Equal(
            "https://origin-shelf.example.invalid/share/origin-registry-shelf-host-audiobook",
            service.GetAudiobookshelfShareForAccount("user-1", "subject-1", "origin-registry-shelf-host", "listen"));
    }

    [Fact]
    public void ListForAccountFailsClosedWhenRegistryAudiobookshelfShareHostIsDisabled()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), "chummer-origin-dossier-publications", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempRoot);
        string indexPath = Path.Combine(tempRoot, "origin-disabled-registry-shelf-host.json");
        OriginDossierArtifactPaths artifacts = CreateGoldArtifacts(tempRoot, "origin-disabled-registry-shelf-host");
        File.WriteAllText(
            indexPath,
            JsonSerializer.Serialize(
                new
                {
                    publications = new[]
                    {
                        BuildIndexEntry(
                            "user-1",
                            "subject-1",
                            "origin-disabled-registry-shelf-host",
                            "Disabled Registry Shelf",
                            "Vanta",
                            artifacts,
                            audiobookshelfHost: "origin-shelf.example.invalid")
                    }
                },
                new JsonSerializerOptions(JsonSerializerDefaults.Web) { WriteIndented = true }));

        var configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_ORIGIN_DOSSIER_PUBLICATION_INDEX"] = indexPath,
                ["CHUMMER_ORIGIN_PROVIDER_ACCOUNT_REGISTRY"] = """
                {
                  "accounts": [
                    {
                      "accountAlias": "ABS_ORIGIN_01",
                      "provider": "Audiobookshelf",
                      "status": "disabled",
                      "roles": ["audiobookshelf", "book_share"],
                      "shareHost": "origin-shelf.example.invalid"
                    }
                  ]
                }
                """
            })
            .Build();
        var service = new OriginDossierPublicationService(
            configuration,
            NullLogger<OriginDossierPublicationService>.Instance);

        OriginDossierPublicationViewModel publication = Assert.Single(service.ListForAccount("user-1", "subject-1"));

        Assert.False(publication.GoldReady);
        Assert.Contains("trusted Audiobookshelf share URL", publication.MissingGoldRequirements);
        Assert.Contains("trusted Audiobookshelf dossier ebook share URL", publication.MissingGoldRequirements);
        Assert.Contains("trusted Audiobookshelf audiobook share URL", publication.MissingGoldRequirements);
        Assert.Null(service.GetAudiobookshelfShareForAccount("user-1", "subject-1", "origin-disabled-registry-shelf-host", "listen"));
    }

    [Fact]
    public void ListForAccountFailsClosedWhenRegistryAudiobookshelfAccountOnlyHasGenericOriginShareRole()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), "chummer-origin-dossier-publications", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempRoot);
        string indexPath = Path.Combine(tempRoot, "origin-generic-share-registry-shelf-host.json");
        OriginDossierArtifactPaths artifacts = CreateGoldArtifacts(tempRoot, "origin-generic-share-registry-shelf-host");
        File.WriteAllText(
            indexPath,
            JsonSerializer.Serialize(
                new
                {
                    publications = new[]
                    {
                        BuildIndexEntry(
                            "user-1",
                            "subject-1",
                            "origin-generic-share-registry-shelf-host",
                            "Generic Share Registry Shelf",
                            "Vanta",
                            artifacts,
                            audiobookshelfHost: "origin-shelf.example.invalid")
                    }
                },
                new JsonSerializerOptions(JsonSerializerDefaults.Web) { WriteIndented = true }));

        var configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_ORIGIN_DOSSIER_PUBLICATION_INDEX"] = indexPath,
                ["CHUMMER_ORIGIN_PROVIDER_ACCOUNT_REGISTRY"] = """
                {
                  "accounts": [
                    {
                      "accountAlias": "ABS_ORIGIN_01",
                      "provider": "Audiobookshelf",
                      "status": "available",
                      "roles": ["origin_share"],
                      "shareHost": "origin-shelf.example.invalid"
                    }
                  ]
                }
                """
            })
            .Build();
        var service = new OriginDossierPublicationService(
            configuration,
            NullLogger<OriginDossierPublicationService>.Instance);

        OriginDossierPublicationViewModel publication = Assert.Single(service.ListForAccount("user-1", "subject-1"));

        Assert.False(publication.GoldReady);
        Assert.Contains("trusted Audiobookshelf share URL", publication.MissingGoldRequirements);
        Assert.Contains("trusted Audiobookshelf dossier ebook share URL", publication.MissingGoldRequirements);
        Assert.Contains("trusted Audiobookshelf audiobook share URL", publication.MissingGoldRequirements);
        Assert.Null(service.GetAudiobookshelfShareForAccount("user-1", "subject-1", "origin-generic-share-registry-shelf-host", "listen"));
    }

    [Fact]
    public void ListForAccountRejectsPrivateOriginDossierWhenAssignedProviderAccountAliasIsOutsideConfiguredLane()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), "chummer-origin-dossier-publications", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempRoot);
        string indexPath = Path.Combine(tempRoot, "origin-wrong-account-alias.json");
        OriginDossierArtifactPaths artifacts = CreateGoldArtifacts(tempRoot, "origin-wrong-account-alias");
        File.WriteAllText(
            indexPath,
            JsonSerializer.Serialize(
                new
                {
                    publications = new[]
                    {
                        BuildIndexEntry(
                            "user-1",
                            "subject-1",
                            "origin-wrong-account-alias",
                            "Wrong Alias",
                            "Vanta",
                            artifacts,
                            providerManuscriptAccountAlias: "INK02_COMMERCIAL",
                            audiobookProviderAccountAlias: OriginAudiobookAccountAlias)
                    }
                },
                new JsonSerializerOptions(JsonSerializerDefaults.Web) { WriteIndented = true }));

        var configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_ORIGIN_DOSSIER_PUBLICATION_INDEX"] = indexPath,
                ["CHUMMER_ORIGIN_MANUSCRIPT_ACCOUNT_ALIASES"] = "INK01_ORIGIN,YB02_CHUMMER_PRIVATE,FIRSTBOOK_PREMIUM",
                ["CHUMMER_ORIGIN_AUDIO_ACCOUNT_ALIASES"] = "UNMIXR_TIBOR_01,INK01_ORIGIN"
            })
            .Build();
        var service = new OriginDossierPublicationService(
            configuration,
            NullLogger<OriginDossierPublicationService>.Instance);

        OriginDossierPublicationViewModel publication = Assert.Single(service.ListForAccount("user-1", "subject-1"));

        Assert.False(publication.GoldReady);
        Assert.Contains("provider manuscript account alias", publication.MissingGoldRequirements);
    }

    [Fact]
    public void ListForAccountRejectsConfiguredAccountAliasWhenReceiptDoesNotBindTheAlias()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), "chummer-origin-dossier-publications", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempRoot);
        string indexPath = Path.Combine(tempRoot, "origin-missing-account-alias-receipt-token.json");
        OriginDossierArtifactPaths artifacts = CreateGoldArtifacts(tempRoot, "origin-missing-account-alias-receipt-token");
        File.WriteAllText(
            artifacts.ProviderManuscriptReceiptPath,
            JsonSerializer.Serialize(
                new
                {
                    operation = "provider_manuscript_import",
                    provider = "Inkfluence",
                    status = "verified",
                    completedAtUtc = DateTimeOffset.UtcNow,
                    deliveredLinks = new[] { "operator_verified_live_run", "provider_receipt_reference:Inkfluence:provider_manuscript_import" },
                    artifactSha256 = new[] { ComputeSha256(artifacts.ProviderManuscriptPath) }
                },
                new JsonSerializerOptions(JsonSerializerDefaults.Web) { WriteIndented = true }));
        File.WriteAllText(
            indexPath,
            JsonSerializer.Serialize(
                new { publications = new[] { BuildIndexEntry("user-1", "subject-1", "origin-missing-account-alias-receipt-token", "Missing Alias Receipt", "Vanta", artifacts) } },
                new JsonSerializerOptions(JsonSerializerDefaults.Web) { WriteIndented = true }));

        var configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_ORIGIN_DOSSIER_PUBLICATION_INDEX"] = indexPath,
                ["CHUMMER_ORIGIN_MANUSCRIPT_ACCOUNT_ALIASES"] = OriginManuscriptAccountAlias,
                ["CHUMMER_ORIGIN_AUDIO_ACCOUNT_ALIASES"] = OriginAudiobookAccountAlias
            })
            .Build();
        var service = new OriginDossierPublicationService(
            configuration,
            NullLogger<OriginDossierPublicationService>.Instance);

        OriginDossierPublicationViewModel publication = Assert.Single(service.ListForAccount("user-1", "subject-1"));

        Assert.False(publication.GoldReady);
        Assert.Contains("provider manuscript account alias", publication.MissingGoldRequirements);
    }

    [Fact]
    public void ListForAccountRejectsConfiguredAccountAliasWhenReceiptOnlyContainsAliasPrefix()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), "chummer-origin-dossier-publications", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempRoot);
        string indexPath = Path.Combine(tempRoot, "origin-spoofed-account-alias-receipt-token.json");
        OriginDossierArtifactPaths artifacts = CreateGoldArtifacts(tempRoot, "origin-spoofed-account-alias-receipt-token");
        File.WriteAllText(
            artifacts.ProviderManuscriptReceiptPath,
            JsonSerializer.Serialize(
                new
                {
                    operation = "provider_manuscript_import",
                    provider = "Inkfluence",
                    status = "verified",
                    completedAtUtc = DateTimeOffset.UtcNow,
                    deliveredLinks = new[]
                    {
                        "operator_verified_live_run",
                        "provider_receipt_reference:Inkfluence:provider_manuscript_import",
                        $"accountAlias: {OriginManuscriptAccountAlias}_FAKE"
                    },
                    artifactSha256 = new[] { ComputeSha256(artifacts.ProviderManuscriptPath) }
                },
                new JsonSerializerOptions(JsonSerializerDefaults.Web) { WriteIndented = true }));
        File.WriteAllText(
            indexPath,
            JsonSerializer.Serialize(
                new { publications = new[] { BuildIndexEntry("user-1", "subject-1", "origin-spoofed-account-alias-receipt-token", "Spoofed Alias Receipt", "Vanta", artifacts) } },
                new JsonSerializerOptions(JsonSerializerDefaults.Web) { WriteIndented = true }));

        var configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_ORIGIN_DOSSIER_PUBLICATION_INDEX"] = indexPath,
                ["CHUMMER_ORIGIN_MANUSCRIPT_ACCOUNT_ALIASES"] = OriginManuscriptAccountAlias,
                ["CHUMMER_ORIGIN_AUDIO_ACCOUNT_ALIASES"] = OriginAudiobookAccountAlias
            })
            .Build();
        var service = new OriginDossierPublicationService(
            configuration,
            NullLogger<OriginDossierPublicationService>.Instance);

        OriginDossierPublicationViewModel publication = Assert.Single(service.ListForAccount("user-1", "subject-1"));

        Assert.False(publication.GoldReady);
        Assert.Contains("provider manuscript account alias", publication.MissingGoldRequirements);
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
    public void ListForAccountRequiresAudiobookshelfReceiptsToBindOriginTaxonomy()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), "chummer-origin-dossier-publications", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempRoot);
        string indexPath = Path.Combine(tempRoot, "origin-wrong-audiobookshelf-taxonomy.json");
        OriginDossierArtifactPaths artifacts = CreateGoldArtifacts(tempRoot, "origin-wrong-audiobookshelf-taxonomy");
        File.WriteAllText(
            artifacts.AudiobookshelfImportReceiptPath,
            JsonSerializer.Serialize(
                new
                {
                    operation = "audiobookshelf_import",
                    provider = "Audiobookshelf",
                    status = "verified",
                    completedAtUtc = DateTimeOffset.UtcNow,
                    originEditionNamespace = "origin.chummer.run/Varga/Mira/Vanta",
                    libraryPath = "origin.chummer.run/Varga/Mira/Vanta/dossier",
                    deliveredLinks = new[] { "operator_verified_live_run", "provider_receipt_reference:Audiobookshelf:audiobookshelf_import", "narrationProvider: Unmixr", $"accountAlias: {OriginAudiobookAccountAlias}" },
                    artifactSha256 = new[] { ComputeSha256(artifacts.AudiobookPath) }
                },
                new JsonSerializerOptions(JsonSerializerDefaults.Web) { WriteIndented = true }));
        File.WriteAllText(
            indexPath,
            JsonSerializer.Serialize(
                new { publications = new[] { BuildIndexEntry("user-1", "subject-1", "origin-wrong-audiobookshelf-taxonomy", "Wrong Taxonomy", "Vanta", artifacts) } },
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

    [Fact]
    public void ListForAccountRequiresTelegramReceiptFromEaAdapterNotTokenOnlyFile()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), "chummer-origin-dossier-publications", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempRoot);
        string indexPath = Path.Combine(tempRoot, "origin-token-only-telegram.json");
        OriginDossierArtifactPaths artifacts = CreateGoldArtifacts(tempRoot, "origin-token-only-telegram");
        File.WriteAllText(
            artifacts.TelegramShareDeliveryReceiptPath,
            JsonSerializer.Serialize(
                new
                {
                    operation = "telegram_share_delivery",
                    provider = "EA Telegram",
                    status = "delivered",
                    deliveredAtUtc = DateTimeOffset.UtcNow,
                    deliveredLinks = new[]
                    {
                        "/account/work/origin-dossiers/origin-token-only-telegram",
                        "/account/work/origin-dossiers/origin-token-only-telegram/read",
                        "/account/work/origin-dossiers/origin-token-only-telegram/listen",
                        "/account/work/origin-dossiers/origin-token-only-telegram/watch",
                        Sha256Text("/account/work/origin-dossiers/origin-token-only-telegram"),
                        Sha256Text("/account/work/origin-dossiers/origin-token-only-telegram/read"),
                        Sha256Text("/account/work/origin-dossiers/origin-token-only-telegram/listen"),
                        Sha256Text("/account/work/origin-dossiers/origin-token-only-telegram/watch"),
                        "origin.chummer.run/Varga/Mira/Vanta",
                        Sha256Text("origin.chummer.run/Varga/Mira/Vanta"),
                        "operator_verified_live_run",
                        "provider_receipt_reference"
                    }
                },
                new JsonSerializerOptions(JsonSerializerDefaults.Web) { WriteIndented = true }));
        File.WriteAllText(
            indexPath,
            JsonSerializer.Serialize(
                new { publications = new[] { BuildIndexEntry("user-1", "subject-1", "origin-token-only-telegram", "Token Only Telegram", "Vanta", artifacts) } },
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

    [Fact]
    public void ListForAccountAcceptsTelegramDeliveryAliasFromRegistry()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), "chummer-origin-dossier-publications", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempRoot);
        string indexPath = Path.Combine(tempRoot, "origin-registry-telegram.json");
        OriginDossierArtifactPaths artifacts = CreateGoldArtifacts(tempRoot, "origin-registry-telegram");
        File.WriteAllText(
            indexPath,
            JsonSerializer.Serialize(
                new { publications = new[] { BuildIndexEntry("user-1", "subject-1", "origin-registry-telegram", "Registry Telegram", "Vanta", artifacts) } },
                new JsonSerializerOptions(JsonSerializerDefaults.Web) { WriteIndented = true }));

        var configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_ORIGIN_DOSSIER_PUBLICATION_INDEX"] = indexPath,
                ["CHUMMER_ORIGIN_PROVIDER_ACCOUNT_REGISTRY"] = $$"""
                {
                  "accounts": [
                    {
                      "accountAlias": "{{OriginTelegramAccountAlias}}",
                      "provider": "Telegram",
                      "status": "available",
                      "roles": ["telegram", "telegram_delivery", "origin_share"]
                    }
                  ]
                }
                """
            })
            .Build();
        var service = new OriginDossierPublicationService(
            configuration,
            NullLogger<OriginDossierPublicationService>.Instance);

        OriginDossierPublicationViewModel publication = Assert.Single(service.ListForAccount("user-1", "subject-1"));

        Assert.True(publication.GoldReady, string.Join(", ", publication.MissingGoldRequirements));
    }

    [Fact]
    public void ListForAccountFailsClosedWhenRegistryTelegramAccountOnlyHasGenericOriginShareRole()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), "chummer-origin-dossier-publications", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempRoot);
        string indexPath = Path.Combine(tempRoot, "origin-generic-share-registry-telegram.json");
        OriginDossierArtifactPaths artifacts = CreateGoldArtifacts(tempRoot, "origin-generic-share-registry-telegram");
        File.WriteAllText(
            indexPath,
            JsonSerializer.Serialize(
                new { publications = new[] { BuildIndexEntry("user-1", "subject-1", "origin-generic-share-registry-telegram", "Generic Share Registry Telegram", "Vanta", artifacts) } },
                new JsonSerializerOptions(JsonSerializerDefaults.Web) { WriteIndented = true }));

        var configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_ORIGIN_DOSSIER_PUBLICATION_INDEX"] = indexPath,
                ["CHUMMER_ORIGIN_PROVIDER_ACCOUNT_REGISTRY"] = $$"""
                {
                  "accounts": [
                    {
                      "accountAlias": "{{OriginTelegramAccountAlias}}",
                      "provider": "Telegram",
                      "status": "available",
                      "roles": ["origin_share"]
                    }
                  ]
                }
                """
            })
            .Build();
        var service = new OriginDossierPublicationService(
            configuration,
            NullLogger<OriginDossierPublicationService>.Instance);

        OriginDossierPublicationViewModel publication = Assert.Single(service.ListForAccount("user-1", "subject-1"));

        Assert.False(publication.GoldReady);
        Assert.Contains("Telegram share delivery receipt path", publication.MissingGoldRequirements);
    }

    [Fact]
    public void ListForAccountPublishesNonSampleRunnerWithRegistryRoutedGoldArtifacts()
    {
        const string projectId = "origin-case-ari-ghost";
        const string familyName = "Case";
        const string givenName = "Ari";
        const string runnerName = "Ghost";
        const string originNamespace = "origin.chummer.run/Case/Ari/Ghost";
        string tempRoot = Path.Combine(Path.GetTempPath(), "chummer-origin-dossier-publications", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempRoot);
        string indexPath = Path.Combine(tempRoot, "origin-non-sample-registry-gold.json");
        OriginDossierArtifactPaths artifacts = CreateGoldArtifacts(
            tempRoot,
            projectId,
            runnerName,
            originNamespace);
        File.WriteAllText(
            indexPath,
            JsonSerializer.Serialize(
                new
                {
                    publications = new[]
                    {
                        BuildIndexEntry(
                            "user-ghost",
                            "subject-ghost",
                            projectId,
                            "Ghost Origin Dossier",
                            runnerName,
                            artifacts,
                            familyName: familyName,
                            givenName: givenName,
                            runnerName: runnerName)
                    }
                },
                new JsonSerializerOptions(JsonSerializerDefaults.Web) { WriteIndented = true }));

        var configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_ORIGIN_DOSSIER_PUBLICATION_INDEX"] = indexPath,
                ["CHUMMER_ORIGIN_PROVIDER_ACCOUNT_REGISTRY"] = $$"""
                {
                  "accounts": [
                    {
                      "accountAlias": "{{OriginManuscriptAccountAlias}}",
                      "provider": "Inkfluence",
                      "status": "available",
                      "roles": ["manuscript", "origin"]
                    },
                    {
                      "accountAlias": "{{OriginAudiobookAccountAlias}}",
                      "provider": "Unmixr",
                      "status": "available",
                      "roles": ["audio", "audiobook", "origin"]
                    },
                    {
                      "accountAlias": "ABS_ORIGIN_01",
                      "provider": "Audiobookshelf",
                      "status": "available",
                      "roles": ["audiobookshelf", "book_share"],
                      "shareHost": "audio.chummer.run"
                    },
                    {
                      "accountAlias": "{{OriginTelegramAccountAlias}}",
                      "provider": "Telegram",
                      "status": "available",
                      "roles": ["telegram", "telegram_delivery", "origin_share"]
                    }
                  ]
                }
                """
            })
            .Build();
        var service = new OriginDossierPublicationService(
            configuration,
            NullLogger<OriginDossierPublicationService>.Instance);

        OriginDossierPublicationViewModel publication = Assert.Single(service.ListForAccount("user-ghost", "subject-ghost"));

        Assert.True(publication.GoldReady, string.Join(", ", publication.MissingGoldRequirements));
        Assert.Equal(originNamespace, publication.OriginEditionNamespace);
        Assert.Equal($"https://chummer.run/account/work/origin-dossiers/{projectId}/read", publication.AudiobookshelfDossierShareUrl);
        Assert.Equal($"https://chummer.run/account/work/origin-dossiers/{projectId}/listen", publication.AudiobookshelfAudiobookShareUrl);
        Assert.Equal($"https://audio.chummer.run/share/{projectId}-dossier", service.GetAudiobookshelfShareForAccount("user-ghost", "subject-ghost", projectId, "read"));
        Assert.Equal($"https://audio.chummer.run/share/{projectId}-audiobook", service.GetAudiobookshelfShareForAccount("user-ghost", "subject-ghost", projectId, "listen"));
    }

    [Fact]
    public void ListForAccountFailsClosedWhenRegistryTelegramDeliveryAccountIsDisabled()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), "chummer-origin-dossier-publications", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempRoot);
        string indexPath = Path.Combine(tempRoot, "origin-disabled-registry-telegram.json");
        OriginDossierArtifactPaths artifacts = CreateGoldArtifacts(tempRoot, "origin-disabled-registry-telegram");
        File.WriteAllText(
            indexPath,
            JsonSerializer.Serialize(
                new { publications = new[] { BuildIndexEntry("user-1", "subject-1", "origin-disabled-registry-telegram", "Disabled Registry Telegram", "Vanta", artifacts) } },
                new JsonSerializerOptions(JsonSerializerDefaults.Web) { WriteIndented = true }));

        var configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_ORIGIN_DOSSIER_PUBLICATION_INDEX"] = indexPath,
                ["CHUMMER_ORIGIN_PROVIDER_ACCOUNT_REGISTRY"] = $$"""
                {
                  "accounts": [
                    {
                      "accountAlias": "{{OriginTelegramAccountAlias}}",
                      "provider": "Telegram",
                      "status": "disabled",
                      "roles": ["telegram", "telegram_delivery", "origin_share"]
                    }
                  ]
                }
                """
            })
            .Build();
        var service = new OriginDossierPublicationService(
            configuration,
            NullLogger<OriginDossierPublicationService>.Instance);

        OriginDossierPublicationViewModel publication = Assert.Single(service.ListForAccount("user-1", "subject-1"));

        Assert.False(publication.GoldReady);
        Assert.Contains("Telegram share delivery receipt path", publication.MissingGoldRequirements);
    }


    [Fact]
    public void ListForAccountRequiresPassingFinalNoFallbackNoSentinelAuditBeforeGoldReady()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), "chummer-origin-dossier-publications", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempRoot);
        string indexPath = Path.Combine(tempRoot, "origin-dossier-publications.json");
        OriginDossierArtifactPaths artifacts = CreateGoldArtifacts(tempRoot, "origin-blocked-final-audit");
        WriteFinalNoFallbackNoSentinelAuditReceipt(
            Path.GetDirectoryName(artifacts.FinalNoFallbackNoSentinelAuditReceiptPath)!,
            Path.GetFileName(artifacts.FinalNoFallbackNoSentinelAuditReceiptPath),
            "origin.chummer.run/Varga/Mira/Vanta",
            status: "blocked");
        File.WriteAllText(
            indexPath,
            JsonSerializer.Serialize(
                new { publications = new[] { BuildIndexEntry("user-1", "subject-1", "origin-blocked-final-audit", "Blocked Final Audit", "Vanta", artifacts) } },
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
        Assert.Contains("final no-fallback/no-sentinel audit receipt path", publication.MissingGoldRequirements);
    }

    private static object BuildIndexEntry(
        string ownerUserId,
        string subjectId,
        string projectId,
        string title,
        string runnerAlias,
        OriginDossierArtifactPaths artifacts,
        string? audiobookshelfShareUrl = null,
        string? providerManuscriptAccountAlias = OriginManuscriptAccountAlias,
        string? audiobookProviderAccountAlias = OriginAudiobookAccountAlias,
        string audiobookshelfHost = "audio.chummer.run",
        string familyName = "Varga",
        string givenName = "Mira",
        string? runnerName = null)
        => new
        {
            ownerUserId,
            subjectId,
            projectId,
            title,
            runnerAlias,
            familyName,
            givenName,
            runnerName = runnerName ?? runnerAlias,
            originEditionNamespace = $"origin.chummer.run/{familyName}/{givenName}/{runnerName ?? runnerAlias}",
            publicationState = "published_for_owner",
            chummerRunOwnerUrl = $"https://chummer.run/account/work/origin-dossiers/{projectId}",
            bookArtifactUrl = $"https://chummer.run/account/work/origin-dossiers/{projectId}/book",
            audiobookshelfShareUrl = audiobookshelfShareUrl ?? $"https://{audiobookshelfHost}/share/{projectId}-audiobook",
            audiobookshelfDossierShareUrl = $"https://{audiobookshelfHost}/share/{projectId}-dossier",
            audiobookshelfAudiobookShareUrl = audiobookshelfShareUrl ?? $"https://{audiobookshelfHost}/share/{projectId}-audiobook",
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
            providerManuscriptAccountAlias,
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
            audiobookProviderAccountAlias,
            artifacts.DossierVideoPath,
            artifacts.DossierVideoReceiptPath,
            artifacts.MoviePosterPath,
            artifacts.MovieSubtitlesPath,
            artifacts.MovieStoryboardPath,
            artifacts.TelegramShareDeliveryReceiptPath,
            artifacts.FinalNoFallbackNoSentinelAuditReceiptPath
        };

    private static OriginDossierArtifactPaths CreateGoldArtifacts(
        string tempRoot,
        string projectId,
        string runnerAlias = "Vanta",
        string originEditionNamespace = "origin.chummer.run/Varga/Mira/Vanta")
    {
        string projectRoot = Path.Combine(tempRoot, projectId);
        Directory.CreateDirectory(projectRoot);
        string sourcePacketPath = WriteArtifact(projectRoot, "approved-source-packet.json", $$"""{"runnerAlias":"{{runnerAlias}}","approvedForExternalProcessing":true}""");
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
            [$"accountAlias: {OriginManuscriptAccountAlias}"],
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
            [
                $"dossierShare: https://audio.chummer.run/share/{projectId}-dossier",
                $"originEditionNamespace: {originEditionNamespace}",
                $"originTaxonomy: {originEditionNamespace}/dossier"
            ],
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
                originEditionNamespace,
                "selected_character_face"
            ],
            artifactPaths: [storySceneCoverPath]);
        string coverConsistencyReceiptPath = WriteCoverConsistencyReceipt(
            projectRoot,
            "cover-consistency.receipt.json",
            originEditionNamespace,
            ComputeSha256(storySceneCoverPath));
        string audiobookPath = WriteArtifact(projectRoot, "audiobook.m4b", "M4B audiobook artifact");
        string audiobookshelfImportReceiptPath = WriteReceipt(
            projectRoot,
            "audiobookshelf-import.receipt.json",
            "audiobookshelf_import",
            "Audiobookshelf",
            [
                "narrationProvider: Unmixr",
                $"accountAlias: {OriginAudiobookAccountAlias}",
                $"originEditionNamespace: {originEditionNamespace}",
                $"originTaxonomy: {originEditionNamespace}/audiobook"
            ],
            artifactPaths: [audiobookPath]);
        string dossierVideoPath = WriteArtifact(projectRoot, "dossier-film.mp4", "MP4 dossier film artifact");
        string moviePosterPath = WriteArtifact(projectRoot, "movie-poster.png", "PNG movie poster artifact");
        string movieSubtitlesPath = WriteArtifact(projectRoot, "subtitles.vtt", "WEBVTT\n\n00:00.000 --> 00:02.000\nOrigin scene.\n");
        string movieStoryboardPath = WriteArtifact(projectRoot, "storyboard.json", """{"sceneId":"clinic-door-rain"}""");
        string dossierVideoReceiptPath = WriteReceipt(
            projectRoot,
            "dossier-film.receipt.json",
            "dossier_video_import",
            "video_lane",
            artifactPaths: [dossierVideoPath]);
        string telegramShareDeliveryReceiptPath = WriteTelegramShareDeliveryReceipt(
            projectRoot,
            "telegram-share.receipt.json",
            projectId,
            originEditionNamespace);
        string finalNoFallbackNoSentinelAuditReceiptPath = WriteFinalNoFallbackNoSentinelAuditReceipt(
            projectRoot,
            "final-no-fallback-no-sentinel.receipt.json",
            originEditionNamespace);

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
            moviePosterPath,
            movieSubtitlesPath,
            movieStoryboardPath,
            telegramShareDeliveryReceiptPath,
            finalNoFallbackNoSentinelAuditReceiptPath);
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

    private static string WriteTelegramShareDeliveryReceipt(
        string projectRoot,
        string fileName,
        string projectId,
        string originEditionNamespace)
    {
        string path = Path.Combine(projectRoot, fileName);
        string ownerPath = $"/account/work/origin-dossiers/{projectId}";
        string readPath = $"{ownerPath}/read";
        string listenPath = $"{ownerPath}/listen";
        string watchPath = $"{ownerPath}/watch";
        File.WriteAllText(
            path,
            JsonSerializer.Serialize(
                new
                {
                    contractName = "ea.telegram_audiobook_live_delivery_receipt.v1",
                    operation = "telegram_share_delivery",
                    provider = "EA Telegram",
                    adapter = "ExecutiveAssistantChannelMessagingService",
                    accountAlias = OriginTelegramAccountAlias,
                    status = "delivered",
                    deliveredAtUtc = DateTimeOffset.UtcNow,
                    telegramMessageIdHashedByEa = true,
                    rawTelegramChatIdIncluded = false,
                    selected_delivery = new
                    {
                        telegram_delivery_status = "sent",
                        telegram_delivery_message_id_present = true,
                        telegram_chat_bound = true,
                        telegram_message_bound = true,
                        origin_edition_link_bundle = new
                        {
                            status = "sent",
                            project_id = projectId,
                            origin_namespace_sha256 = Sha256Text(originEditionNamespace),
                            telegram_delivery_status = "sent",
                            telegram_message_id_present = true,
                            all_required_links_present = true,
                            raw_urls_exposed = false,
                            open_in_chummer_url_sha256 = Sha256Text(ownerPath),
                            read_url_sha256 = Sha256Text(readPath),
                            listen_url_sha256 = Sha256Text(listenPath),
                            watch_url_sha256 = Sha256Text(watchPath)
                        }
                    },
                    deliveredLinks = new[]
                    {
                        ownerPath,
                        readPath,
                        listenPath,
                        watchPath,
                        Sha256Text(ownerPath),
                        Sha256Text(readPath),
                        Sha256Text(listenPath),
                        Sha256Text(watchPath),
                        originEditionNamespace,
                        Sha256Text(originEditionNamespace),
                        $"accountAlias: {OriginTelegramAccountAlias}",
                        "operator_verified_live_run",
                        "provider_receipt_reference"
                    }
                },
                new JsonSerializerOptions(JsonSerializerDefaults.Web) { WriteIndented = true }));
        return path;
    }

    private static string WriteFinalNoFallbackNoSentinelAuditReceipt(
        string projectRoot,
        string fileName,
        string originEditionNamespace,
        string status = "pass")
    {
        string path = Path.Combine(projectRoot, fileName);
        string[] requiredSurfaces =
        [
            "approved_canon_packet",
            "provider_manuscript",
            "humanizer_receipt",
            "humanizer_quality_receipt",
            "cover",
            "ebook",
            "pdf",
            "pdf_cover_receipt",
            "dossier_audiobookshelf_receipt",
            "m4b_provider_gate",
            "cover_consistency",
            "movie",
            "movie_receipt",
            "gap_audit",
            "real_m4b_artifact",
            "audiobookshelf_audiobook_receipt"
        ];

        File.WriteAllText(
            path,
            JsonSerializer.Serialize(
                new
                {
                    contractName = "chummer.origin_edition.final_no_fallback_bundle_audit.v1",
                    operation = "origin_edition_final_no_fallback_bundle_audit",
                    provider = "Chummer",
                    status,
                    goldEligible = string.Equals(status, "pass", StringComparison.OrdinalIgnoreCase),
                    completedAtUtc = DateTimeOffset.UtcNow,
                    @namespace = originEditionNamespace,
                    blockedSurfaces = string.Equals(status, "pass", StringComparison.OrdinalIgnoreCase)
                        ? Array.Empty<string>()
                        : ["real_m4b_artifact"],
                    surfaces = requiredSurfaces
                        .Select(surface => new
                        {
                            name = surface,
                            status = string.Equals(status, "pass", StringComparison.OrdinalIgnoreCase) ? "pass" : "blocked"
                        })
                        .ToArray()
                },
                new JsonSerializerOptions(JsonSerializerDefaults.Web) { WriteIndented = true }));
        return path;
    }

    private static string WriteCoverConsistencyReceipt(
        string projectRoot,
        string fileName,
        string originEditionNamespace,
        string coverSha256)
    {
        string path = Path.Combine(projectRoot, fileName);
        string[] requiredSurfaces =
        [
            "chummer_hero_cover",
            "dossier_cover_asset",
            "ebook_embedded_cover",
            "pdf_cover_embedding",
            "audiobook_cover_asset",
            "m4b_cover_embedding",
            "audiobookshelf_dossier_cover",
            "audiobookshelf_audiobook_cover",
            "movie_poster"
        ];

        File.WriteAllText(
            path,
            JsonSerializer.Serialize(
                new
                {
                    contractName = "chummer.origin_edition.cover_consistency_audit.v1",
                    operation = "origin_edition_cover_consistency",
                    provider = "Chummer",
                    status = "pass",
                    goldEligible = true,
                    completedAtUtc = DateTimeOffset.UtcNow,
                    @namespace = originEditionNamespace,
                    expectedCoverSha256 = coverSha256,
                    blockedSurfaces = Array.Empty<string>(),
                    surfaces = requiredSurfaces
                        .Select(surface => new { name = surface, status = "pass", sha256 = coverSha256 })
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

    private static string Sha256Text(string value)
        => Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(value))).ToLowerInvariant();

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
        string MoviePosterPath,
        string MovieSubtitlesPath,
        string MovieStoryboardPath,
        string TelegramShareDeliveryReceiptPath,
        string FinalNoFallbackNoSentinelAuditReceiptPath);
}
