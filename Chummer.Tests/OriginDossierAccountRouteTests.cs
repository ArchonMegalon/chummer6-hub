using System.Net;
using System.Net.Http.Headers;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Chummer.Run.Api;
using Chummer.Run.Api.Controllers;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.ViewModels;
using Chummer.Run.Contracts.Community;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.FileProviders;
using Microsoft.Extensions.Hosting;
using Xunit;

namespace Chummer.Tests;

public sealed class OriginDossierAccountRouteTests
{
    [Fact]
    public async Task OriginDossierDetailPageShowsOnlyTheSignedInOwnersGoldEdition()
    {
        using var fixture = OriginDossierRouteFixture.Create();
        fixture.ImportGoldPublication("origin-route", fixture.SubjectId);
        AccountsController controller = fixture.CreateController();

        IActionResult result = await controller.OriginDossierDetailPage("origin-route", CancellationToken.None);

        ViewResult view = Assert.IsType<ViewResult>(result);
        Assert.Equal("~/Views/Accounts/OriginDossier.cshtml", view.ViewName);
        OriginDossierPublicationDetailPageViewModel model = Assert.IsType<OriginDossierPublicationDetailPageViewModel>(view.Model);
        Assert.Equal("origin-route", model.Publication.ProjectId);
        Assert.True(model.Publication.GoldReady, string.Join(", ", model.Publication.MissingGoldRequirements));
        Assert.Equal("origin.chummer.run/Varga/Mira/Route-Runner", model.Publication.OriginEditionNamespace);
        Assert.Equal("https://chummer.run/account/work/origin-dossiers/origin-route/read", model.Publication.AudiobookshelfDossierShareUrl);
        Assert.Equal("https://chummer.run/account/work/origin-dossiers/origin-route/listen", model.Publication.AudiobookshelfShareUrl);
        Assert.Equal("https://chummer.run/account/work/origin-dossiers/origin-route/listen", model.Publication.AudiobookshelfAudiobookShareUrl);
        Assert.Equal("https://chummer.run/account/work/origin-dossiers/origin-route/cover", model.Publication.StorySceneCoverUrl);
        Assert.NotNull(model.Publication.ArtifactCapability);
        Assert.Equal("origin-dossier", model.Publication.ArtifactCapability!.HorizonId);
        Assert.Equal("origin-dossier-media", model.Publication.ArtifactCapability.CapabilityId);
        Assert.Equal("dossier_media", model.Publication.ArtifactCapability.ArtifactKind);
        Assert.Equal("origin-dossier:origin-route:media", model.Publication.ArtifactCapability.SourceRef);
        Assert.Equal("private", model.Publication.ArtifactCapability.Visibility);
        Assert.NotNull(model.Publication.SharedArtifacts);
        Assert.Equal("/api/v1/public/horizons/capabilities", model.Publication.SharedArtifacts!.PublicCapabilityCatalogHref);
        Assert.Null(model.Publication.SharedArtifacts.PublicCapabilityHealthHref);
        Assert.Null(model.Publication.SharedArtifacts.PublicRequestReceiptDetailHrefTemplate);
        Assert.Equal("/api/v1/horizons/capabilities/me?horizonId=origin-dossier&artifactKindOrCapabilityId=origin-dossier-media", model.Publication.SharedArtifacts.SignedInCapabilityCatalogHref);
        Assert.Equal("/api/v1/horizons/quotas/me?horizonId=origin-dossier&artifactKindOrCapabilityId=origin-dossier-media", model.Publication.SharedArtifacts.SignedInQuotaCatalogHref);
        Assert.Equal("/api/v1/horizons/artifact-requests/me?horizonId=origin-dossier&artifactKindOrCapabilityId=origin-dossier-media", model.Publication.SharedArtifacts.SignedInRequestReceiptHref);
        Assert.Equal("/api/v1/horizons/artifact-requests/me/{requestId}", model.Publication.SharedArtifacts.SignedInRequestReceiptDetailHrefTemplate);
        string serialized = JsonSerializer.Serialize(model.Publication.ArtifactCapability);
        Assert.DoesNotContain("First Book", serialized, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("MarkupGo", serialized, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("vidBoard", serialized, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("Soundmadeseen", serialized, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void OriginDossierViewExposesReadListenWatchAndCanonAuditTabs()
    {
        string view = File.ReadAllText(Path.Combine(
            FindRepositoryRoot(),
            "Chummer.Run.Api",
            "Views",
            "Accounts",
            "OriginDossier.cshtml"));

        Assert.Contains("data-origin-edition-tabs", view, StringComparison.Ordinal);
        Assert.Contains("href=\"#origin-edition-read\"", view, StringComparison.Ordinal);
        Assert.Contains("href=\"#origin-edition-listen\"", view, StringComparison.Ordinal);
        Assert.Contains("href=\"#origin-edition-watch\"", view, StringComparison.Ordinal);
        Assert.Contains("href=\"#origin-edition-canon-audit\"", view, StringComparison.Ordinal);
        Assert.Contains("Read in Audiobookshelf", view, StringComparison.Ordinal);
        Assert.Contains("Listen in Audiobookshelf", view, StringComparison.Ordinal);
        Assert.Contains("Watch scene movie", view, StringComparison.Ordinal);
    }

    private static string FindRepositoryRoot()
    {
        DirectoryInfo? directory = new(AppContext.BaseDirectory);
        while (directory is not null)
        {
            if (Directory.Exists(Path.Combine(directory.FullName, "Chummer.Run.Api")))
                return directory.FullName;

            directory = directory.Parent;
        }

        throw new DirectoryNotFoundException("Could not locate Chummer.Run.Api from the test output directory.");
    }

    [Fact]
    public async Task OriginDossierArtifactsRequireSignedInOwnerAndRouteReadListenWatchThroughChummerRun()
    {
        using var fixture = OriginDossierRouteFixture.Create();
        OriginDossierRouteArtifacts artifacts = fixture.ImportGoldPublication("origin-route", fixture.SubjectId);
        AccountsController controller = fixture.CreateController();

        IActionResult coverResult = await controller.OriginDossierArtifact("origin-route", "cover", CancellationToken.None);
        PhysicalFileResult cover = Assert.IsType<PhysicalFileResult>(coverResult);
        Assert.Equal(artifacts.StorySceneCoverPath, cover.FileName);
        Assert.Equal("image/png", cover.ContentType);
        Assert.True(cover.EnableRangeProcessing);

        IActionResult listenResult = await controller.OriginDossierArtifact("origin-route", "listen", CancellationToken.None);
        RedirectResult listen = Assert.IsType<RedirectResult>(listenResult);
        Assert.Equal("https://audio.chummer.run/share/origin-route-audiobook", listen.Url);
        Assert.StartsWith("horizon-artifact-", controller.Response.Headers["X-Horizon-Artifact-Request-Id"].ToString(), StringComparison.Ordinal);

        IActionResult readResult = await controller.OriginDossierArtifact("origin-route", "read", CancellationToken.None);
        RedirectResult read = Assert.IsType<RedirectResult>(readResult);
        Assert.Equal("https://audio.chummer.run/share/origin-route-dossier", read.Url);

        IActionResult watchResult = await controller.OriginDossierArtifact("origin-route", "watch", CancellationToken.None);
        PhysicalFileResult watch = Assert.IsType<PhysicalFileResult>(watchResult);
        Assert.Equal(artifacts.DossierVideoPath, watch.FileName);
        Assert.Equal("video/mp4", watch.ContentType);

        IReadOnlyList<HorizonArtifactRequestReceipt> receipts = fixture.ArtifactRequestReceipts.ListRecent("origin-dossier", fixture.SubjectId, limit: 10);
        Assert.Equal(4, receipts.Count);
        Assert.Contains(receipts, receipt => receipt.Status == "accepted" && receipt.SourceRef == "origin-dossier:origin-route:cover" && receipt.Quota is null && receipt.Visibility == "private");
        Assert.Contains(receipts, receipt => receipt.Status == "accepted" && receipt.SourceRef == "origin-dossier:origin-route:listen" && receipt.Quota is null && receipt.Visibility == "private");
        Assert.Contains(receipts, receipt => receipt.Status == "accepted" && receipt.SourceRef == "origin-dossier:origin-route:read" && receipt.Quota is null && receipt.Visibility == "private");
        Assert.Contains(receipts, receipt => receipt.Status == "accepted" && receipt.SourceRef == "origin-dossier:origin-route:watch" && receipt.Quota is null && receipt.Visibility == "private");

        AccountsController anonymous = fixture.CreateController(authenticated: false);
        IActionResult anonymousResult = await anonymous.OriginDossierArtifact("origin-route", "listen", CancellationToken.None);
        RedirectResult login = Assert.IsType<RedirectResult>(anonymousResult);
        Assert.StartsWith("/login?next=", login.Url, StringComparison.Ordinal);
        Assert.Contains(Uri.EscapeDataString("/account/work/origin-dossiers/origin-route/listen"), login.Url, StringComparison.Ordinal);
    }

    [Fact]
    public async Task OriginDossierArtifactRoutesReturnNotFoundForNonOwnerEvenWhenGoldReady()
    {
        using var fixture = OriginDossierRouteFixture.Create();
        fixture.ImportGoldPublication("origin-other-owner", "subject.other-owner");
        AccountsController controller = fixture.CreateController();

        IActionResult coverResult = await controller.OriginDossierArtifact("origin-other-owner", "cover", CancellationToken.None);
        IActionResult listenResult = await controller.OriginDossierArtifact("origin-other-owner", "listen", CancellationToken.None);

        Assert.IsType<NotFoundResult>(coverResult);
        Assert.IsType<NotFoundResult>(listenResult);
    }

    private sealed class OriginDossierRouteFixture : IDisposable
    {
        private const string AccessToken = "origin-route-token";
        private readonly ServiceProvider _provider;

        private OriginDossierRouteFixture(string root, string subjectId, ServiceProvider provider)
        {
            Root = root;
            SubjectId = subjectId;
            _provider = provider;
        }

        public string Root { get; }

        public string SubjectId { get; }

        public HorizonArtifactRequestReceiptStore ArtifactRequestReceipts
            => _provider.GetRequiredService<HorizonArtifactRequestReceiptStore>();

        public static OriginDossierRouteFixture Create()
        {
            string root = Path.Combine(Path.GetTempPath(), "chummer-origin-dossier-route-tests", Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(root);
            string subjectId = "subject.origin-route";
            IConfiguration configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_COMMUNITY_STORE_PATH"] = Path.Combine(root, "community.json"),
                    ["CHUMMER_INSTALL_LINKING_STORE_PATH"] = Path.Combine(root, "install-linking.json"),
                    ["CHUMMER_SUPPORT_STORE_PATH"] = Path.Combine(root, "support.json"),
                    ["CHUMMER_PUBLIC_CONCIERGE_STORE_PATH"] = Path.Combine(root, "public-concierge.json"),
                    ["CHUMMER_KARMA_FORGE_STORE_PATH"] = Path.Combine(root, "karma-forge.json"),
                    ["CHUMMER_BRILLIANT_DIRECTORIES_BILLING_STORE_PATH"] = Path.Combine(root, "bd-billing.json"),
                    ["CHUMMER_MYFIRSTBOOK_USAGE_STORE_PATH"] = Path.Combine(root, "myfirstbook-usage.json"),
                    ["CHUMMER_PAYFUNNELS_BILLING_STORE_PATH"] = Path.Combine(root, "payfunnels-billing.json"),
                    ["CHUMMER_ORIGIN_DOSSIER_PUBLICATION_INDEX"] = Path.Combine(root, "origin-dossier-publications.json"),
                    ["CHUMMER_HORIZON_ARTIFACT_REQUEST_RECEIPT_STORE_PATH"] = Path.Combine(root, "horizon-artifact-request-receipts.json"),
                    ["CHUMMER_PUBLIC_BASE_URL"] = "https://chummer.run",
                    ["CHUMMER_LOCAL_E2E_ACCESS_TOKEN"] = AccessToken,
                    ["CHUMMER_LOCAL_E2E_SUBJECT_ID"] = subjectId,
                    ["CHUMMER_LOCAL_E2E_DISPLAY_NAME"] = "Route Runner",
                    ["CHUMMER_LOCAL_E2E_EMAIL"] = "route.runner@example.invalid",
                    ["IDENTITY_SERVICE_BASE_URL"] = "https://identity.example.test"
                })
                .Build();

            ServiceCollection services = new();
            services.AddSingleton(configuration);
            services.AddSingleton<IHostEnvironment>(new TestHostEnvironment(root));
            services.AddLogging();
            services.AddControllersWithViews();
            services.AddDataProtection().PersistKeysToFileSystem(new DirectoryInfo(Path.Combine(root, "data-protection-keys")));
            services
                .AddHubPublicGuideContext()
                .AddHubAccountsAndCommunityContext()
                .AddHubCampaignSpineContext()
                .AddHubControlAndSupportContext()
                .AddHubInstallAndOrchestrationAdapters();
            return new OriginDossierRouteFixture(root, subjectId, services.BuildServiceProvider());
        }

        public AccountsController CreateController(bool authenticated = true)
        {
            AccountsController controller = ActivatorUtilities.CreateInstance<AccountsController>(_provider);
            DefaultHttpContext httpContext = new()
            {
                RequestServices = _provider
            };
            httpContext.Request.Host = new HostString("localhost");
            httpContext.Connection.RemoteIpAddress = IPAddress.Loopback;
            if (authenticated)
            {
                httpContext.Request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", AccessToken).ToString();
            }

            controller.ControllerContext = new ControllerContext
            {
                HttpContext = httpContext
            };
            return controller;
        }

        public OriginDossierRouteArtifacts ImportGoldPublication(string projectId, string subjectId)
        {
            OriginDossierRouteArtifacts artifacts = CreateGoldArtifacts(projectId);
            HubUserDto user = new(
                UserId: $"user-{subjectId}",
                SubjectId: subjectId,
                DisplayName: "Route Runner",
                Handle: "route-runner",
                Visibility: "private",
                Timezone: "UTC",
                CountryCode: "US",
                LinkedPrincipals: [subjectId],
                GroupIds: [],
                CreatedAtUtc: DateTimeOffset.UtcNow,
                UpdatedAtUtc: DateTimeOffset.UtcNow);
            _provider.GetRequiredService<OriginDossierPublicationService>().UpsertForAccount(
                user,
                subjectId,
                new OriginDossierPublicationImportRequest(
                    ProjectId: projectId,
                    Title: "Route Runner Origin Dossier",
                    RunnerAlias: "Route Runner",
                    FamilyName: "Varga",
                    GivenName: "Mira",
                    RunnerName: "Route Runner",
                    OriginEditionNamespace: "origin.chummer.run/Varga/Mira/Route-Runner",
                    PublicationState: "published_for_owner",
                    BookArtifactUrl: $"https://chummer.run/account/work/origin-dossiers/{projectId}/book",
                    AudiobookshelfShareUrl: $"https://audio.chummer.run/share/{projectId}-audiobook",
                    AudiobookshelfDossierShareUrl: $"https://audio.chummer.run/share/{projectId}-dossier",
                    AudiobookshelfAudiobookShareUrl: $"https://audio.chummer.run/share/{projectId}-audiobook",
                    DossierVideoUrl: $"https://chummer.run/account/work/origin-dossiers/{projectId}/video",
                    StorySceneCoverUrl: $"https://chummer.run/account/work/origin-dossiers/{projectId}/cover",
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
            return artifacts;
        }

        private OriginDossierRouteArtifacts CreateGoldArtifacts(string projectId)
        {
            string projectRoot = Path.Combine(Root, projectId);
            Directory.CreateDirectory(projectRoot);
            string sourcePacketPath = WriteArtifact(projectRoot, "approved-source-packet.json", """{"runnerAlias":"Route Runner","approvedForExternalProcessing":true}""");
            string providerManuscriptPath = WriteArtifact(projectRoot, "provider-manuscript.md", "Provider-authored Origin Dossier manuscript.");
            string bookArtifactPath = WriteArtifact(projectRoot, "book.pdf", "%PDF-1.7\nOrigin Dossier route test book artifact\n");
            string ebookArtifactPath = WriteArtifact(projectRoot, "ebook.epub", "EPUB route test ebook artifact with embedded cover");
            string storySceneCoverPath = WriteArtifact(projectRoot, "story-scene-cover.png", "PNG route test story scene cover artifact");
            string audiobookPath = WriteArtifact(projectRoot, "audiobook.m4b", "M4B route test audiobook artifact");
            string dossierVideoPath = WriteArtifact(projectRoot, "dossier-film.mp4", "MP4 route test dossier film artifact");
            string moviePosterPath = WriteArtifact(projectRoot, "movie-poster.png", "PNG route test movie poster artifact");
            string movieSubtitlesPath = WriteArtifact(projectRoot, "subtitles.vtt", "WEBVTT\n\n00:00.000 --> 00:02.000\nRain made the clinic sign stutter.\n");
            string movieStoryboardPath = WriteArtifact(projectRoot, "storyboard.json", """{"sceneId":"clinic-door-rain","shots":["threshold","clinic","sedan"]}""");

            return new OriginDossierRouteArtifacts(
                SourcePacketPath: sourcePacketPath,
                SourcePacketReceiptPath: WriteReceipt(
                    projectRoot,
                    "approved-source-packet.receipt.json",
                    "origin_source_packet_approval",
                    "Chummer",
                    ["approved_source_packet", "external_processing_consent"],
                    [sourcePacketPath]),
                CanonAuditReceiptPath: WriteReceipt(
                    projectRoot,
                    "chummer-canon-audit.receipt.json",
                    "chummer_canon_audit",
                    "Chummer",
                    ["canon_audit_passed", "hard_conflicts:0", "privacy_findings:0"],
                    [sourcePacketPath, providerManuscriptPath]),
                ProviderManuscriptPath: providerManuscriptPath,
                ProviderManuscriptReceiptPath: WriteReceipt(
                    projectRoot,
                    "provider-manuscript.receipt.json",
                    "provider_manuscript_import",
                    "Inkfluence",
                    artifactPaths: [providerManuscriptPath]),
                HumanizerReceiptPath: WriteReceipt(
                    projectRoot,
                    "undetectable-humanizer.receipt.json",
                    "undetectable_humanizer_postprocess",
                    "Undetectable Humanizer",
                    artifactPaths: [providerManuscriptPath]),
                BookArtifactPath: bookArtifactPath,
                BookArtifactReceiptPath: WriteReceipt(
                    projectRoot,
                    "book.receipt.json",
                    "book_artifact_import",
                    "Inkfluence",
                    artifactPaths: [bookArtifactPath]),
                StorySceneCoverPath: storySceneCoverPath,
                StorySceneCoverReceiptPath: WriteReceipt(
                    projectRoot,
                    "story-scene-cover.receipt.json",
                    "selected_face_scene_render",
                    "rendered_cover_lane",
                    [
                        $"/account/work/origin-dossiers/{projectId}",
                        $"/account/work/origin-dossiers/{projectId}/cover",
                        "origin.chummer.run/Varga/Mira/Route-Runner",
                        "selected_character_face"
                    ],
                    [storySceneCoverPath]),
                EbookArtifactPath: ebookArtifactPath,
                EbookAudiobookshelfImportReceiptPath: WriteReceipt(
                    projectRoot,
                    "audiobookshelf-dossier-import.receipt.json",
                    "audiobookshelf_dossier_import",
                    "Audiobookshelf",
                    [
                        "dossierShare: https://audio.chummer.run/share/origin-route-dossier",
                        "origin.chummer.run/Varga/Mira/Route-Runner",
                        "origin.chummer.run/Varga/Mira/Route-Runner/dossier"
                    ],
                    [ebookArtifactPath]),
                CoverConsistencyReceiptPath: WriteCoverConsistencyReceipt(
                    projectRoot,
                    "cover-consistency.receipt.json",
                    "origin.chummer.run/Varga/Mira/Route-Runner",
                    ComputeSha256(storySceneCoverPath)),
                AudiobookPath: audiobookPath,
                AudiobookshelfImportReceiptPath: WriteReceipt(
                    projectRoot,
                    "audiobookshelf-import.receipt.json",
                    "audiobookshelf_import",
                    "Audiobookshelf",
                    [
                        "narrationProvider: Unmixr",
                        "origin.chummer.run/Varga/Mira/Route-Runner",
                        "origin.chummer.run/Varga/Mira/Route-Runner/audiobook"
                    ],
                    [audiobookPath]),
                DossierVideoPath: dossierVideoPath,
                DossierVideoReceiptPath: WriteReceipt(
                    projectRoot,
                    "dossier-film.receipt.json",
                    "dossier_video_import",
                    "video_lane",
                    artifactPaths: [dossierVideoPath]),
                TelegramShareDeliveryReceiptPath: WriteTelegramShareReceipt(
                    projectRoot,
                    "telegram-share.receipt.json",
                    projectId,
                    "origin.chummer.run/Varga/Mira/Route-Runner"),
                FinalNoFallbackNoSentinelAuditReceiptPath: WriteFinalNoFallbackNoSentinelAuditReceipt(
                    projectRoot,
                    "final-no-fallback-no-sentinel.receipt.json",
                    "origin.chummer.run/Varga/Mira/Route-Runner"),
                MoviePosterPath: moviePosterPath,
                MovieSubtitlesPath: movieSubtitlesPath,
                MovieStoryboardPath: movieStoryboardPath);
        }

        public void Dispose()
        {
            _provider.Dispose();
            try
            {
                Directory.Delete(Root, recursive: true);
            }
            catch (IOException)
            {
            }
            catch (UnauthorizedAccessException)
            {
            }
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
            List<string> receiptLinks = (deliveredLinks ?? []).ToList();
            if (!string.Equals(provider, "Chummer", StringComparison.OrdinalIgnoreCase))
            {
                receiptLinks.Add("operator_verified_live_run");
                receiptLinks.Add($"provider_receipt_reference:{provider}:{operation}");
            }

            File.WriteAllText(
                path,
                System.Text.Json.JsonSerializer.Serialize(
                    new
                    {
                        operation,
                        provider,
                        status = "verified",
                        completedAtUtc = DateTimeOffset.UtcNow,
                        deliveredLinks = receiptLinks,
                        artifactSha256 = (artifactPaths ?? [])
                            .Select(ComputeSha256)
                            .ToArray()
                    },
                    new System.Text.Json.JsonSerializerOptions(System.Text.Json.JsonSerializerDefaults.Web) { WriteIndented = true }));
            return path;
        }

        private static string WriteTelegramShareReceipt(
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
                System.Text.Json.JsonSerializer.Serialize(
                    new
                    {
                        contractName = "ea.telegram_audiobook_live_delivery_receipt.v1",
                        operation = "telegram_share_delivery",
                        provider = "Telegram",
                        adapter = "ExecutiveAssistantChannelMessagingService",
                        status = "delivered",
                        completedAtUtc = DateTimeOffset.UtcNow,
                        telegramMessageIdHashedByEa = true,
                        rawTelegramChatIdIncluded = false,
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
                            "operator_verified_live_run",
                            "provider_receipt_reference:Telegram:telegram_share_delivery"
                        },
                        linkBundle = new
                        {
                            project_id = projectId,
                            origin_namespace_sha256 = Sha256Text(originEditionNamespace),
                            open_in_chummer_url_sha256 = Sha256Text(ownerPath),
                            read_url_sha256 = Sha256Text(readPath),
                            listen_url_sha256 = Sha256Text(listenPath),
                            watch_url_sha256 = Sha256Text(watchPath),
                            all_required_links_present = true,
                            raw_urls_exposed = false,
                            telegram_delivery_status = "sent",
                            telegram_message_id_present = true
                        }
                    },
                    new System.Text.Json.JsonSerializerOptions(System.Text.Json.JsonSerializerDefaults.Web) { WriteIndented = true }));
            return path;
        }

        private static string WriteFinalNoFallbackNoSentinelAuditReceipt(
            string projectRoot,
            string fileName,
            string originEditionNamespace)
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
                System.Text.Json.JsonSerializer.Serialize(
                    new
                    {
                        contractName = "chummer.origin_edition.final_no_fallback_bundle_audit.v1",
                        operation = "origin_edition_final_no_fallback_bundle_audit",
                        provider = "Chummer",
                        status = "pass",
                        goldEligible = true,
                        completedAtUtc = DateTimeOffset.UtcNow,
                        @namespace = originEditionNamespace,
                        blockedSurfaces = Array.Empty<string>(),
                        surfaces = requiredSurfaces
                            .Select(surface => new { name = surface, status = "pass" })
                            .ToArray()
                    },
                    new System.Text.Json.JsonSerializerOptions(System.Text.Json.JsonSerializerDefaults.Web) { WriteIndented = true }));
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
                System.Text.Json.JsonSerializer.Serialize(
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
                    new System.Text.Json.JsonSerializerOptions(System.Text.Json.JsonSerializerDefaults.Web) { WriteIndented = true }));
            return path;
        }

        private static string ComputeSha256(string path)
        {
            using FileStream stream = File.OpenRead(path);
            return Convert.ToHexString(SHA256.HashData(stream)).ToLowerInvariant();
        }

        private static string Sha256Text(string value)
            => Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(value))).ToLowerInvariant();
    }

    private sealed record OriginDossierRouteArtifacts(
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

    private sealed class TestHostEnvironment : IHostEnvironment
    {
        public TestHostEnvironment(string root)
        {
            ContentRootPath = root;
            ContentRootFileProvider = new PhysicalFileProvider(root);
        }

        public string EnvironmentName { get; set; } = Environments.Development;

        public string ApplicationName { get; set; } = "Chummer.Tests";

        public string ContentRootPath { get; set; }

        public IFileProvider ContentRootFileProvider { get; set; }
    }
}
