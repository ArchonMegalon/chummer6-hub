using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Chummer.Run.Api;
using Chummer.Run.Api.Controllers;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.Services.InstallLinking;
using Chummer.Run.Contracts.PublicSurface;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class GenerationBoundDownloadAuthorizationTests
{
    [Fact]
    public void CredentialedArtifactHrefUsesImmutableGenerationRoute()
    {
        var artifact = new PublicReleaseArtifactDto(
            Id: GenerationFixture.ArtifactId,
            Platform: "macos",
            Url: "/downloads/files/chummer-shared-installer.dmg",
            Sha256: new string('a', 64),
            FileName: GenerationFixture.FileName,
            InstallAccessClass: "account_required");
        var manifest = new PublicReleaseManifestDto(
            Version: "run-a",
            Channel: "preview",
            PublishedAt: DateTimeOffset.UnixEpoch,
            Downloads: [artifact])
        {
            GenerationId = "generation-a"
        };

        string href = PublicLandingController.BuildCredentialBoundArtifactHref(
            manifest,
            artifact,
            $"/downloads/file/{artifact.Id}");

        Assert.Equal(
            "/downloads/g/generation-a/install/shared-account-required-installer",
            href);
    }

    [Fact]
    public void ExplicitlyPublicArtifactHrefUsesImmutableGenerationFileRoute()
    {
        var artifact = new PublicReleaseArtifactDto(
            Id: GenerationFixture.ArtifactId,
            Platform: "macos",
            Url: "/downloads/files/chummer-shared-installer.dmg",
            Sha256: new string('a', 64),
            FileName: GenerationFixture.FileName,
            InstallAccessClass: "open_public");
        var manifest = new PublicReleaseManifestDto(
            Version: "run-a",
            Channel: "preview",
            PublishedAt: DateTimeOffset.UnixEpoch,
            Downloads: [artifact])
        {
            GenerationId = "generation-a"
        };

        string href = PublicLandingController.BuildCredentialBoundArtifactHref(
            manifest,
            artifact,
            $"/downloads/file/{artifact.Id}");

        Assert.Equal(
            "/downloads/g/generation-a/files/chummer-shared-installer.dmg",
            href);
    }

    [Fact]
    public async Task ProtectedGenerationFileFailsClosedWithoutGenerationCredential()
    {
        using GenerationFixture fixture = new();
        fixture.SetConfiguration("CHUMMER_PUBLIC_FORCE_ACCOUNT_REQUIRED_DOWNLOADS", "true");
        fixture.SetQuery(null, null);

        IActionResult result = await fixture.Controller.DownloadGenerationFile(
            "generation-a",
            GenerationFixture.FileName,
            CancellationToken.None);

        ObjectResult blocked = Assert.IsType<ObjectResult>(result);
        Assert.Equal(StatusCodes.Status409Conflict, blocked.StatusCode);
    }

    [Fact]
    public async Task GenerationInstallRouteValidatesExactGenerationAndDigestBeforeVerifiedServe()
    {
        using GenerationFixture fixture = new();
        (PublicReleaseManifestDto manifestA, PublicReleaseArtifactDto artifactA) = fixture.LoadArtifact("generation-a");
        DownloadDispatchResult dispatchA = fixture.InstallLinking.IssueDownload(
            manifestA,
            artifactA,
            "user-generation-a",
            "subject-generation-a");
        Assert.NotNull(dispatchA.ClaimTicket);
        string claimA = dispatchA.ClaimTicket!.ClaimCode;

        fixture.Activate(GenerationFixture.ProtectedGenerationId);
        fixture.SetQuery("claimCode", claimA);
        IActionResult generationB = await fixture.Controller.DownloadGenerationArtifact(
            GenerationFixture.ProtectedGenerationId,
            GenerationFixture.ArtifactId,
            CancellationToken.None);
        Assert.IsType<UnauthorizedObjectResult>(generationB);

        fixture.SetQuery("claimCode", claimA);
        IActionResult retainedA = await fixture.Controller.DownloadGenerationArtifact(
            "generation-a",
            GenerationFixture.ArtifactId,
            CancellationToken.None);
        Assert.Equal("artifact-a", await ReadFileResultAsync(retainedA));
    }

    [Fact]
    public async Task GenerationAClaimCannotReadCurrentBButCanReadRetainedA()
    {
        using GenerationFixture fixture = new();
        (PublicReleaseManifestDto manifestA, PublicReleaseArtifactDto artifactA) = fixture.LoadArtifact("generation-a");
        DownloadDispatchResult dispatchA = fixture.InstallLinking.IssueDownload(
            manifestA,
            artifactA,
            "user-generation-a",
            "subject-generation-a");
        Assert.NotNull(dispatchA.ClaimTicket);
        string claimA = dispatchA.ClaimTicket!.ClaimCode;

        fixture.Activate(GenerationFixture.ProtectedGenerationId);
        fixture.SetQuery("claimCode", claimA);
        IActionResult currentB = await fixture.Controller.DownloadFile(GenerationFixture.FileName, CancellationToken.None);
        Assert.IsType<UnauthorizedObjectResult>(currentB);

        fixture.SetQuery("claimCode", claimA);
        IActionResult retainedA = await fixture.Controller.DownloadGenerationFile(
            "generation-a",
            GenerationFixture.FileName,
            CancellationToken.None);
        Assert.Equal("artifact-a", await ReadFileResultAsync(retainedA));

        (PublicReleaseManifestDto manifestB, PublicReleaseArtifactDto artifactB) = fixture.LoadArtifact(
            GenerationFixture.ProtectedGenerationId);
        DownloadDispatchResult dispatchB = fixture.InstallLinking.IssueDownload(
            manifestB,
            artifactB,
            "user-generation-b",
            "subject-generation-b");
        Assert.NotNull(dispatchB.ClaimTicket);
        fixture.SetQuery("claimCode", dispatchB.ClaimTicket!.ClaimCode);
        IActionResult correctlyBoundCurrentB = await fixture.Controller.DownloadFile(
            GenerationFixture.FileName,
            CancellationToken.None);
        Assert.Equal("artifact-protected-b", await ReadFileResultAsync(correctlyBoundCurrentB));
    }

    [Fact]
    public async Task GenerationABootstrapTicketCannotReadBButCanReadRetainedA()
    {
        using GenerationFixture fixture = new();
        (PublicReleaseManifestDto manifestA, PublicReleaseArtifactDto artifactA) = fixture.LoadArtifact("generation-a");
        InstallBootstrapTicketIssueResult ticketA = fixture.InstallBootstrapTickets.IssueBound(
            artifactA.Id,
            [new InstallBootstrapArtifactBinding(artifactA.Id, artifactA.Sha256)],
            manifestA.GenerationId!,
            "user-generation-a",
            "subject-generation-a");

        fixture.Activate("generation-b");
        fixture.SetQuery("ticket", ticketA.Ticket);
        IActionResult currentB = await fixture.Controller.DownloadFile(GenerationFixture.FileName, CancellationToken.None);
        Assert.IsType<UnauthorizedObjectResult>(currentB);

        fixture.SetQuery("ticket", ticketA.Ticket);
        IActionResult retainedA = await fixture.Controller.DownloadGenerationFile(
            "generation-a",
            GenerationFixture.FileName,
            CancellationToken.None);
        Assert.Equal("artifact-a", await ReadFileResultAsync(retainedA));
    }

    [Fact]
    public async Task RoleBoundTicketCannotCollapsePrimaryBindingIntoPayloadOrMetadata()
    {
        using GenerationFixture fixture = new();
        (PublicReleaseManifestDto manifest, PublicReleaseArtifactDto artifact) = fixture.LoadArtifact("generation-a");
        InstallBootstrapTicketIssueResult primaryOnly = fixture.InstallBootstrapTickets.IssueBound(
            artifact.Id,
            [new InstallBootstrapArtifactBinding(artifact.Id, artifact.Sha256)],
            manifest.GenerationId!,
            "user-generation-a",
            "subject-generation-a");

        fixture.SetQuery("ticket", primaryOnly.Ticket);
        IActionResult payloadDenied = await fixture.Controller.DownloadGenerationArtifactPayload(
            "generation-a",
            GenerationFixture.ArtifactId,
            CancellationToken.None);
        Assert.IsType<UnauthorizedObjectResult>(payloadDenied);

        ReleaseShelfSnapshot snapshot = fixture.ManifestService.CaptureShelfGeneration("generation-a");
        IReadOnlyList<InstallBootstrapArtifactBinding> bindings = fixture.DeliveryPolicy.BuildCredentialBindings(
            snapshot,
            [artifact]);
        InstallBootstrapTicketIssueResult roleBound = fixture.InstallBootstrapTickets.IssueBound(
            artifact.Id,
            bindings,
            manifest.GenerationId!,
            "user-generation-a",
            "subject-generation-a");

        fixture.SetQuery("ticket", roleBound.Ticket);
        IActionResult payload = await fixture.Controller.DownloadGenerationArtifactPayload(
            "generation-a",
            GenerationFixture.ArtifactId,
            CancellationToken.None);
        Assert.Equal("payload-a", await ReadFileResultAsync(payload));

        fixture.SetQuery("ticket", roleBound.Ticket);
        IActionResult metadata = await fixture.Controller.DownloadGenerationArtifactPayloadMetadata(
            "generation-a",
            GenerationFixture.ArtifactId,
            CancellationToken.None);
        FileStreamResult metadataFile = Assert.IsType<FileStreamResult>(metadata);
        Assert.Equal("application/json; charset=utf-8", metadataFile.ContentType);
        await metadataFile.FileStream.DisposeAsync();
    }

    [Fact]
    public async Task GlobalRevocationInvalidatesOpenCurrentAndRetainedClaimAndTicketPaths()
    {
        using GenerationFixture fixture = new();
        (PublicReleaseManifestDto manifestA, PublicReleaseArtifactDto artifactA) = fixture.LoadArtifact("generation-a");
        DownloadDispatchResult dispatchA = fixture.InstallLinking.IssueDownload(
            manifestA,
            artifactA,
            "user-generation-a",
            "subject-generation-a");
        InstallBootstrapTicketIssueResult ticketA = fixture.InstallBootstrapTickets.IssueBound(
            artifactA.Id,
            fixture.DeliveryPolicy.BuildCredentialBindings(
                fixture.ManifestService.CaptureShelfGeneration("generation-a"),
                [artifactA]),
            manifestA.GenerationId!,
            "user-generation-a",
            "subject-generation-a");
        fixture.Activate("generation-b");
        fixture.RevokeArtifact(GenerationFixture.ArtifactId);

        fixture.SetQuery(null, null);
        IActionResult openCurrent = await fixture.Controller.DownloadFile(
            GenerationFixture.FileName,
            CancellationToken.None);
        Assert.Equal(StatusCodes.Status410Gone, Assert.IsType<ObjectResult>(openCurrent).StatusCode);

        fixture.SetQuery("claimCode", dispatchA.ClaimTicket!.ClaimCode);
        IActionResult retainedClaim = await fixture.Controller.DownloadGenerationArtifact(
            "generation-a",
            GenerationFixture.ArtifactId,
            CancellationToken.None);
        Assert.Equal(StatusCodes.Status410Gone, Assert.IsType<ObjectResult>(retainedClaim).StatusCode);

        fixture.SetQuery("ticket", ticketA.Ticket);
        IActionResult retainedTicket = await fixture.Controller.DownloadGenerationArtifactPayload(
            "generation-a",
            GenerationFixture.ArtifactId,
            CancellationToken.None);
        Assert.Equal(StatusCodes.Status410Gone, Assert.IsType<ObjectResult>(retainedTicket).StatusCode);
    }

    [Fact]
    public void GlobalRevocationBlocksCurrentAndRetainedWindowsSupplementalRoutes()
    {
        using GenerationFixture fixture = new();
        fixture.Activate("generation-b");
        fixture.RevokeArtifact(GenerationFixture.WindowsProofArtifactId);

        fixture.SetQuery(null, null);
        IActionResult current = fixture.Controller.DownloadWindowsProofInstaller(
            GenerationFixture.WindowsProofFileName);
        Assert.Equal(StatusCodes.Status410Gone, Assert.IsType<ObjectResult>(current).StatusCode);

        fixture.SetQuery(null, null);
        IActionResult retained = fixture.Controller.DownloadGenerationWindowsProofInstallerByArtifactId(
            "generation-a",
            GenerationFixture.WindowsProofArtifactId);
        Assert.Equal(StatusCodes.Status410Gone, Assert.IsType<ObjectResult>(retained).StatusCode);
    }

    [Fact]
    public async Task UpstreamDigestRevocationBlocksCurrentAndRetainedAurSidecars()
    {
        using GenerationFixture fixture = new();
        fixture.Activate("generation-b");
        (_, PublicReleaseArtifactDto artifactB) = fixture.LoadArtifact("generation-b");
        fixture.RevokeDigest(artifactB.Sha256);
        fixture.SetQuery(null, null);
        IActionResult current = await fixture.Controller.DownloadFile(
            GenerationFixture.AurPkgbuildFileName,
            CancellationToken.None);
        Assert.Equal(StatusCodes.Status410Gone, Assert.IsType<ObjectResult>(current).StatusCode);

        (_, PublicReleaseArtifactDto artifactA) = fixture.LoadArtifact("generation-a");
        fixture.RevokeDigest(artifactA.Sha256);
        fixture.SetQuery(null, null);
        IActionResult retained = await fixture.Controller.DownloadGenerationFile(
            "generation-a",
            GenerationFixture.AurPkgbuildFileName,
            CancellationToken.None);
        Assert.Equal(StatusCodes.Status410Gone, Assert.IsType<ObjectResult>(retained).StatusCode);
    }

    [Fact]
    public async Task EstablishedKillSwitchAndForcedAccountPolicyApplyToLayoutV1CurrentAndRetainedRoutes()
    {
        using GenerationFixture fixture = new();
        fixture.Activate("generation-b");
        fixture.SetConfiguration("CHUMMER_PUBLIC_DISABLED_ARTIFACT_IDS", GenerationFixture.ArtifactId);
        fixture.SetQuery(null, null);
        ReleaseShelfSnapshot disabledSnapshot = fixture.ManifestService.CaptureShelfSnapshot();
        ArtifactDeliveryResolution disabledResolution = fixture.DeliveryPolicy.ResolveByPath(
            disabledSnapshot,
            GenerationFixture.FileName);
        Assert.Equal(ArtifactDeliveryFailure.Revoked, disabledResolution.Failure);
        IActionResult disabled = await fixture.Controller.DownloadFile(
            GenerationFixture.FileName,
            CancellationToken.None);
        Assert.Equal(StatusCodes.Status410Gone, Assert.IsType<ObjectResult>(disabled).StatusCode);

        fixture.SetConfiguration("CHUMMER_PUBLIC_DISABLED_ARTIFACT_IDS", null);
        fixture.SetConfiguration("CHUMMER_PUBLIC_FORCE_ACCOUNT_REQUIRED_DOWNLOADS", "true");
        fixture.SetQuery(null, null);
        IActionResult forcedCurrent = await fixture.Controller.DownloadFile(
            GenerationFixture.FileName,
            CancellationToken.None);
        Assert.IsType<RedirectResult>(forcedCurrent);

        fixture.SetQuery(null, null);
        IActionResult forcedRetained = await fixture.Controller.DownloadGenerationFile(
            "generation-b",
            GenerationFixture.FileName,
            CancellationToken.None);
        Assert.Equal(StatusCodes.Status409Conflict, Assert.IsType<ObjectResult>(forcedRetained).StatusCode);
    }

    [Fact]
    public async Task ChannelWideCurrentRevocationBlocksArtifactOnlyPresentInRetainedGeneration()
    {
        using GenerationFixture fixture = new();
        fixture.WriteAndActivateChannelWideRevokedGeneration();
        fixture.SetQuery(null, null);

        ReleaseShelfSnapshot retainedSnapshot = fixture.ManifestService.CaptureShelfGeneration(
            "generation-a");
        PublicReleaseManifestDto retainedManifest = fixture.ManifestService.LoadManifest(retainedSnapshot);
        Assert.Single(retainedManifest.Downloads, item => item.Id == GenerationFixture.ArtifactId);
        ArtifactDeliveryResolution retainedResolution = fixture.DeliveryPolicy.ResolveByArtifactId(
            retainedSnapshot,
            GenerationFixture.ArtifactId);
        Assert.False(retainedResolution.Allowed);
        Assert.Equal(ArtifactDeliveryFailure.Revoked, retainedResolution.Failure);

        IActionResult retained = await fixture.Controller.DownloadGenerationArtifact(
            "generation-a",
            GenerationFixture.ArtifactId,
            CancellationToken.None);

        Assert.Equal(StatusCodes.Status410Gone, Assert.IsType<ObjectResult>(retained).StatusCode);
        Assert.Equal(
            "generation-a",
            fixture.ManifestService.CaptureShelfSnapshot().GenerationId);
        Assert.Equal(
            "generation-revoked",
            fixture.ManifestService.CaptureUnpinnedActiveShelfSnapshot().GenerationId);
    }

    [Fact]
    public async Task CompletionClaimsStayBoundToPromotedGenerationWhenCurrentShelfAdvances()
    {
        using GenerationFixture fixture = new();
        fixture.Activate(GenerationFixture.ProtectedGenerationId);
        var resultA = new ReleaseBundlePromotionResult(
            Version: "run-a",
            Channel: "preview",
            PublishedAt: DateTimeOffset.Parse("2026-07-15T12:00:00Z"),
            PromotedArtifactIds: [GenerationFixture.ArtifactId],
            DownloadsUrl: "/downloads",
            InstallDispatchUrls:
            [
                $"/downloads/g/generation-a/install/{GenerationFixture.ArtifactId}"
            ],
            DirectFileUrls: [],
            GenerationId: "generation-a",
            ActivationReceiptId: "activation-generation-a");
        var claims = new ReleaseUploadTicketClaims(
            SubjectId: "subject-release-operator",
            DisplayName: "Release operator",
            Email: "operator@example.test",
            IssuedAtUtc: DateTimeOffset.UtcNow,
            ExpiresAtUtc: DateTimeOffset.UtcNow.AddHours(1),
            TicketId: "ticket-generation-a");

        ReleaseBundlePromotionResult attached = fixture.InternalController.AttachSignedInInstallClaims(
            resultA,
            claims);

        ReleasePromotionInstallClaim claimA = Assert.Single(attached.SignedInInstallClaims!);
        Assert.StartsWith(
            $"/downloads/g/generation-a/install/{GenerationFixture.ArtifactId}",
            claimA.InstallDispatchUrl,
            StringComparison.Ordinal);
        Assert.Contains("claimCode=", claimA.InstallDispatchUrl, StringComparison.Ordinal);

        fixture.SetQuery("claimCode", claimA.ClaimCode);
        IActionResult currentB = await fixture.Controller.DownloadGenerationArtifact(
            GenerationFixture.ProtectedGenerationId,
            GenerationFixture.ArtifactId,
            CancellationToken.None);
        Assert.IsType<UnauthorizedObjectResult>(currentB);

        fixture.SetQuery("claimCode", claimA.ClaimCode);
        IActionResult retainedA = await fixture.Controller.DownloadGenerationArtifact(
            "generation-a",
            GenerationFixture.ArtifactId,
            CancellationToken.None);
        Assert.Equal("artifact-a", await ReadFileResultAsync(retainedA));
    }

    private static async Task<string> ReadFileResultAsync(IActionResult result)
    {
        FileStreamResult file = Assert.IsType<FileStreamResult>(result);
        await using Stream stream = file.FileStream;
        using StreamReader reader = new(stream, Encoding.UTF8);
        return await reader.ReadToEndAsync();
    }

    private sealed class GenerationFixture : IDisposable
    {
        public const string ArtifactId = "shared-account-required-installer";
        public const string FileName = "chummer-shared-installer.dmg";
        public const string PayloadFileName = "chummer-shared-payload.zip";
        public const string ProtectedGenerationId = "generation-protected-b";
        public const string WindowsProofArtifactId = "avalonia-win-x64-installer";
        public const string WindowsProofFileName = "chummer-avalonia-win-x64-installer.exe";
        public const string AurPkgbuildFileName = "chummer6-bin.PKGBUILD";
        private const string PublishedAt = "2026-07-15T12:00:00Z";

        private readonly string _root = Path.Combine(
            Path.GetTempPath(),
            "generation-bound-download-auth-tests",
            Guid.NewGuid().ToString("N"));
        private readonly string _downloadsRoot;
        private readonly Dictionary<string, GenerationMetadata> _generations = new(StringComparer.Ordinal);
        private readonly ServiceProvider _serviceProvider;
        private readonly IHttpContextAccessor _httpContextAccessor;

        public GenerationFixture()
        {
            _downloadsRoot = Path.Combine(_root, "downloads");
            Directory.CreateDirectory(_downloadsRoot);
            WriteGeneration("generation-a", "run-a", "artifact-a", "payload-a", "account_required");
            WriteGeneration("generation-b", "run-b", "artifact-b", "payload-b", "open_public");
            WriteGeneration(
                ProtectedGenerationId,
                "run-protected-b",
                "artifact-protected-b",
                "payload-protected-b",
                "account_required");
            Activate("generation-a");

            Configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_DOWNLOADS_SOURCE_ROOT"] = _downloadsRoot,
                    ["CHUMMER_PUBLIC_CANON_ROOT"] = RepoPaths.Root,
                    ["CHUMMER_INSTALL_LINKING_STORE_PATH"] = Path.Combine(_root, "install-linking.json"),
                    ["CHUMMER_RELEASE_UPLOAD_SESSION_ROOT"] = Path.Combine(_root, "upload-sessions"),
                    ["CHUMMER_COMMUNITY_STORE_PATH"] = Path.Combine(_root, "community.json"),
                    ["CHUMMER_RELEASE_REGISTRY_CURRENT_URL"] = string.Empty,
                    ["CHUMMER_HUB_REGISTRY_BASE_URL"] = string.Empty,
                    ["CHUMMER_WINDOWS_PROOF_LEGACY_SHELF_FALLBACK"] = "true",
                    ["IDENTITY_SERVICE_BASE_URL"] = "http://127.0.0.1:9"
                })
                .Build();

            IConfiguration configuration = Configuration;

            var services = new ServiceCollection();
            services.AddSingleton<IConfiguration>(configuration);
            services.AddHubPublicGuideContext();
            _serviceProvider = services.BuildServiceProvider();
            _httpContextAccessor = _serviceProvider.GetRequiredService<IHttpContextAccessor>();
            ManifestService = _serviceProvider.GetRequiredService<PublicReleaseManifestService>();
            IDataProtectionProvider dataProtection = DataProtectionProvider.Create(
                new DirectoryInfo(Path.Combine(_root, "keys")));
            InstallLinking = new InstallLinkingService(
                new InstallLinkingStore(
                    configuration,
                    dataProtection,
                    NullLogger<InstallLinkingStore>.Instance),
                configuration);
            InstallBootstrapTickets = new InstallBootstrapTicketService(dataProtection, configuration);
            DeliveryPolicy = _serviceProvider.GetRequiredService<ArtifactDeliveryPolicy>();
            var accounts = new AccountService(
                new CommunityStore(configuration, NullLogger<CommunityStore>.Instance));
            InternalController = new InternalReleaseBundlesController(
                new ReleaseBundlePromotionService(
                    configuration,
                    NullLogger<ReleaseBundlePromotionService>.Instance),
                new ReleaseBundleUploadSessionService(
                    configuration,
                    NullLogger<ReleaseBundleUploadSessionService>.Instance),
                configuration,
                new ReleaseUploadTicketService(dataProtection, configuration),
                ManifestService,
                accounts,
                InstallLinking);
            var releaseSelection = new ReleaseSelectionService(new PublicCanonFileLoader(configuration));
            Controller = new DownloadsCompatibilityController(
                ManifestService,
                new WindowsProofInstallerService(configuration),
                new AurPackageCatalogService(configuration),
                releaseSelection,
                InstallLinking,
                InstallBootstrapTickets,
                new HubIdentityClient(new HttpClient(), configuration, NullLogger<HubIdentityClient>.Instance),
                configuration,
                NullLogger<DownloadsCompatibilityController>.Instance,
                DeliveryPolicy);
            SetQuery(null, null);
        }

        public PublicReleaseManifestService ManifestService { get; }
        public InstallLinkingService InstallLinking { get; }
        public InstallBootstrapTicketService InstallBootstrapTickets { get; }
        public IConfigurationRoot Configuration { get; }
        public ArtifactDeliveryPolicy DeliveryPolicy { get; }
        public DownloadsCompatibilityController Controller { get; }
        public InternalReleaseBundlesController InternalController { get; }

        public (PublicReleaseManifestDto Manifest, PublicReleaseArtifactDto Artifact) LoadArtifact(string generationId)
        {
            SetQuery(null, null);
            ReleaseShelfSnapshot snapshot = ManifestService.CaptureShelfGeneration(generationId);
            PublicReleaseManifestDto manifest = ManifestService.LoadManifest(snapshot);
            return (manifest, Assert.Single(manifest.Downloads, item => item.Id == ArtifactId));
        }

        public void SetQuery(string? name, string? value)
        {
            var context = new DefaultHttpContext();
            if (!string.IsNullOrWhiteSpace(name) && value is not null)
            {
                context.Request.QueryString = QueryString.Create(name, value);
            }

            Controller.ControllerContext = new ControllerContext { HttpContext = context };
            _httpContextAccessor.HttpContext = context;
        }

        public void RevokeArtifact(string artifactId)
            => Configuration["CHUMMER_RELEASE_REVOKED_ARTIFACT_IDS"] = artifactId;

        public void RevokeDigest(string sha256)
            => Configuration["CHUMMER_RELEASE_REVOKED_SHA256"] = sha256;

        public void SetConfiguration(string key, string? value)
            => Configuration[key] = value;

        public void WriteAndActivateChannelWideRevokedGeneration()
        {
            const string generationId = "generation-revoked";
            const string version = "run-revoked";
            string generationRoot = Path.Combine(_downloadsRoot, "generations", generationId);
            string filesRoot = Path.Combine(generationRoot, "files");
            Directory.CreateDirectory(filesRoot);
            File.WriteAllText(
                Path.Combine(filesRoot, "channel-revocation.json"),
                JsonSerializer.Serialize(new { status = "revoked" }));
            string canonicalPath = Path.Combine(
                generationRoot,
                ReleaseShelfGenerationStore.CanonicalManifestFileName);
            string compatibilityPath = Path.Combine(
                generationRoot,
                ReleaseShelfGenerationStore.CompatibilityManifestFileName);
            File.WriteAllText(
                canonicalPath,
                JsonSerializer.Serialize(new Dictionary<string, object?>
                {
                    ["generationId"] = generationId,
                    ["product"] = "chummer",
                    ["channelId"] = "preview",
                    ["version"] = version,
                    ["publishedAt"] = PublishedAt,
                    ["status"] = "revoked",
                    ["effectiveRolloutState"] = "revoked",
                    ["artifacts"] = Array.Empty<object>()
                }));
            File.WriteAllText(
                compatibilityPath,
                JsonSerializer.Serialize(new Dictionary<string, object?>
                {
                    ["generationId"] = generationId,
                    ["version"] = version,
                    ["channel"] = "preview",
                    ["publishedAt"] = PublishedAt,
                    ["status"] = "revoked",
                    ["downloads"] = Array.Empty<object>()
                }));
            var metadata = new GenerationMetadata(
                Version: version,
                CanonicalSha256: Sha256(canonicalPath),
                CompatibilitySha256: Sha256(compatibilityPath),
                InventoryDigest: ReleaseShelfGenerationStore.ComputeInventoryDigest(generationRoot));
            _generations[generationId] = metadata;
            Dictionary<string, object?> candidate = BuildPointer(
                generationId,
                metadata,
                "chummer.release-shelf.activation-candidate/v1");
            candidate["contractName"] = "chummer.release-shelf-activation-candidate";
            candidate["inventory"] = ReleaseShelfGenerationStore.BuildInventory(generationRoot);
            File.WriteAllText(
                Path.Combine(generationRoot, "activation-candidate.json"),
                JsonSerializer.Serialize(candidate));
            Activate(generationId);
        }

        public void Activate(string generationId)
        {
            string pointerPath = Path.Combine(
                _downloadsRoot,
                ReleaseShelfGenerationStore.CurrentPointerFileName);
            byte[]? previousPointerBytes = File.Exists(pointerPath)
                ? File.ReadAllBytes(pointerPath)
                : null;
            File.WriteAllText(
                Path.Combine(_downloadsRoot, ReleaseShelfGenerationStore.LayoutMarkerFileName),
                "release-shelf-layout-v1\n");
            GenerationMetadata metadata = _generations[generationId];
            byte[] targetPointerBytes = JsonSerializer.SerializeToUtf8Bytes(
                BuildPointer(generationId, metadata, "chummer.release-shelf.current/v1"));
            File.WriteAllBytes(pointerPath, targetPointerBytes);
            WriteCommittedActivationJournal(
                _downloadsRoot,
                targetPointerBytes,
                previousPointerBytes);
        }

        public void Dispose()
        {
            _httpContextAccessor.HttpContext = null;
            _serviceProvider.Dispose();
            if (Directory.Exists(_root))
            {
                Directory.Delete(_root, recursive: true);
            }
        }

        private void WriteGeneration(
            string generationId,
            string version,
            string artifactText,
            string payloadText,
            string installAccessClass)
        {
            string generationRoot = Path.Combine(_downloadsRoot, "generations", generationId);
            string filesRoot = Path.Combine(generationRoot, "files");
            Directory.CreateDirectory(filesRoot);
            byte[] artifactBytes = Encoding.UTF8.GetBytes(artifactText);
            string artifactPath = Path.Combine(filesRoot, FileName);
            File.WriteAllBytes(artifactPath, artifactBytes);
            string artifactSha256 = Convert.ToHexStringLower(SHA256.HashData(artifactBytes));
            byte[] payloadBytes = Encoding.UTF8.GetBytes(payloadText);
            string payloadPath = Path.Combine(filesRoot, PayloadFileName);
            File.WriteAllBytes(payloadPath, payloadBytes);
            string payloadSha256 = Convert.ToHexStringLower(SHA256.HashData(payloadBytes));
            string payloadUrl = $"/downloads/g/{generationId}/files/{PayloadFileName}";
            File.WriteAllText(
                Path.Combine(filesRoot, PayloadFileName + ".json"),
                JsonSerializer.Serialize(new Dictionary<string, object?>
                {
                    ["contractName"] = "chummer6-ui.windows_bootstrap_payload",
                    ["fileName"] = PayloadFileName,
                    ["downloadUrl"] = payloadUrl,
                    ["sha256"] = payloadSha256,
                    ["sizeBytes"] = payloadBytes.Length,
                    ["installerFileName"] = FileName,
                    ["releaseVersion"] = version
                }));
            WriteWindowsProofInstaller(generationRoot, version);
            WriteAurCatalog(
                generationRoot,
                generationId,
                artifactSha256,
                artifactBytes.LongLength);

            var canonical = new Dictionary<string, object?>
            {
                ["generationId"] = generationId,
                ["product"] = "chummer",
                ["channelId"] = "preview",
                ["version"] = version,
                ["publishedAt"] = PublishedAt,
                ["status"] = "published",
                ["artifacts"] = new object[]
                {
                    new Dictionary<string, object?>
                    {
                        ["artifactId"] = ArtifactId,
                        ["head"] = "avalonia",
                        ["platform"] = "macos",
                        ["rid"] = "osx-arm64",
                        ["arch"] = "arm64",
                        ["kind"] = "dmg",
                        ["platformLabel"] = "Shared account-required installer",
                        ["fileName"] = FileName,
                        ["downloadUrl"] = $"/downloads/g/{generationId}/install/{ArtifactId}",
                        ["payloadFileName"] = PayloadFileName,
                        ["payloadDownloadUrl"] = payloadUrl,
                        ["payloadSha256"] = payloadSha256,
                        ["payloadSizeBytes"] = payloadBytes.Length,
                        ["sha256"] = artifactSha256,
                        ["sizeBytes"] = artifactBytes.Length,
                        ["installAccessClass"] = installAccessClass
                    }
                }
            };
            var compatibility = new Dictionary<string, object?>
            {
                ["generationId"] = generationId,
                ["version"] = version,
                ["channel"] = "preview",
                ["publishedAt"] = PublishedAt,
                ["status"] = "published",
                ["downloads"] = new object[]
                {
                    new Dictionary<string, object?>
                    {
                        ["id"] = ArtifactId,
                        ["platform"] = "macos",
                        ["url"] = $"/downloads/g/{generationId}/install/{ArtifactId}",
                        ["payloadFileName"] = PayloadFileName,
                        ["payloadDownloadUrl"] = payloadUrl,
                        ["payloadSha256"] = payloadSha256,
                        ["payloadSizeBytes"] = payloadBytes.Length,
                        ["sha256"] = artifactSha256,
                        ["sizeBytes"] = artifactBytes.Length,
                        ["head"] = "avalonia",
                        ["platformId"] = "macos",
                        ["rid"] = "osx-arm64",
                        ["arch"] = "arm64",
                        ["kind"] = "dmg",
                        ["fileName"] = FileName,
                        ["installAccessClass"] = installAccessClass
                    }
                }
            };

            string canonicalPath = Path.Combine(generationRoot, ReleaseShelfGenerationStore.CanonicalManifestFileName);
            string compatibilityPath = Path.Combine(generationRoot, ReleaseShelfGenerationStore.CompatibilityManifestFileName);
            File.WriteAllText(canonicalPath, JsonSerializer.Serialize(canonical));
            File.WriteAllText(compatibilityPath, JsonSerializer.Serialize(compatibility));
            var metadata = new GenerationMetadata(
                Version: version,
                CanonicalSha256: Sha256(canonicalPath),
                CompatibilitySha256: Sha256(compatibilityPath),
                InventoryDigest: ReleaseShelfGenerationStore.ComputeInventoryDigest(generationRoot));
            _generations[generationId] = metadata;

            Dictionary<string, object?> candidate = BuildPointer(
                generationId,
                metadata,
                "chummer.release-shelf.activation-candidate/v1");
            candidate["contractName"] = "chummer.release-shelf-activation-candidate";
            candidate["inventory"] = ReleaseShelfGenerationStore.BuildInventory(generationRoot);
            File.WriteAllText(
                Path.Combine(generationRoot, "activation-candidate.json"),
                JsonSerializer.Serialize(candidate));
        }

        private static void WriteWindowsProofInstaller(string generationRoot, string releaseVersion)
        {
            string proofRoot = Path.Combine(generationRoot, "proof", "windows");
            string signingRoot = Path.Combine(generationRoot, "signing");
            Directory.CreateDirectory(proofRoot);
            Directory.CreateDirectory(signingRoot);
            byte[] installerBytes = Encoding.UTF8.GetBytes(
                "proof-installer\0ChummerInstaller.Payload.zip\0Samples/Legacy/Soma-Career.chum5\0tail");
            File.WriteAllBytes(Path.Combine(proofRoot, WindowsProofFileName), installerBytes);
            string sha256 = Convert.ToHexStringLower(SHA256.HashData(installerBytes));
            File.WriteAllText(
                Path.Combine(signingRoot, "signing-avalonia-win-x64.receipt.json"),
                JsonSerializer.Serialize(new
                {
                    contractName = "chummer6-ui.desktop_artifact_signing",
                    generatedAt = "2026-06-19T12:01:00Z",
                    platform = "windows",
                    app = "avalonia",
                    rid = "win-x64",
                    releaseChannel = "preview",
                    releaseVersion,
                    signingStatus = "pass",
                    notarizationStatus = (string?)null,
                    artifacts = new[]
                    {
                        new
                        {
                            fileName = WindowsProofFileName,
                            sha256,
                            kind = "installer",
                            signingStatus = "pass",
                            notarizationStatus = (string?)null
                        }
                    }
                }));
        }

        private static void WriteAurCatalog(
            string generationRoot,
            string generationId,
            string upstreamSha256,
            long upstreamSizeBytes)
        {
            string filesRoot = Path.Combine(generationRoot, "files");
            string sourceArchivePath = Path.Combine(filesRoot, "chummer6-bin-aur-source.tar.gz");
            string pkgbuildPath = Path.Combine(filesRoot, AurPkgbuildFileName);
            string srcinfoPath = Path.Combine(filesRoot, "chummer6-bin.SRCINFO");
            File.WriteAllText(sourceArchivePath, "aur-source-" + generationId);
            File.WriteAllText(pkgbuildPath, "pkgbuild-" + generationId);
            File.WriteAllText(srcinfoPath, "srcinfo-" + generationId);
            string prefix = $"/downloads/g/{generationId}/files/";
            File.WriteAllText(
                Path.Combine(generationRoot, "aur-packages.json"),
                JsonSerializer.Serialize(new
                {
                    generationId,
                    packages = new[]
                    {
                        new
                        {
                            id = "chummer6-bin",
                            packageName = "chummer6-bin",
                            packageVersion = "20260715.120000",
                            title = "Arch / CachyOS",
                            summary = "Generation-bound AUR package.",
                            platformLabel = "Arch / CachyOS",
                            installCommand = "makepkg -si",
                            sourceArchiveFileName = Path.GetFileName(sourceArchivePath),
                            sourceArchiveUrl = prefix + Path.GetFileName(sourceArchivePath),
                            sourceArchiveSha256 = Sha256(sourceArchivePath),
                            sourceArchiveSizeBytes = new FileInfo(sourceArchivePath).Length,
                            pkgbuildFileName = Path.GetFileName(pkgbuildPath),
                            pkgbuildUrl = prefix + Path.GetFileName(pkgbuildPath),
                            pkgbuildSha256 = Sha256(pkgbuildPath),
                            srcinfoFileName = Path.GetFileName(srcinfoPath),
                            srcinfoUrl = prefix + Path.GetFileName(srcinfoPath),
                            srcinfoSha256 = Sha256(srcinfoPath),
                            upstreamArtifactId = ArtifactId,
                            upstreamArtifactFileName = FileName,
                            upstreamArtifactUrl = prefix + FileName,
                            upstreamArtifactSha256 = upstreamSha256,
                            upstreamArtifactSizeBytes = upstreamSizeBytes
                        }
                    }
                }));
        }

        private static Dictionary<string, object?> BuildPointer(
            string generationId,
            GenerationMetadata metadata,
            string schemaVersion)
            => new()
            {
                ["schemaVersion"] = schemaVersion,
                ["generationId"] = generationId,
                ["releaseVersion"] = metadata.Version,
                ["channel"] = "preview",
                ["publishedAt"] = PublishedAt,
                ["manifests"] = new Dictionary<string, object?>
                {
                    ["canonical"] = new Dictionary<string, object?>
                    {
                        ["path"] = $"/downloads/g/{generationId}/{ReleaseShelfGenerationStore.CanonicalManifestFileName}",
                        ["sha256"] = metadata.CanonicalSha256
                    },
                    ["compatibility"] = new Dictionary<string, object?>
                    {
                        ["path"] = $"/downloads/g/{generationId}/{ReleaseShelfGenerationStore.CompatibilityManifestFileName}",
                        ["sha256"] = metadata.CompatibilitySha256
                    }
                },
                ["inventoryDigest"] = $"sha256:{metadata.InventoryDigest}",
                ["activatedAt"] = PublishedAt,
                ["activationReceiptId"] = $"activation-{generationId}"
            };

        private static string Sha256(string path)
        {
            using FileStream stream = File.OpenRead(path);
            return Convert.ToHexStringLower(SHA256.HashData(stream));
        }

        private static void WriteCommittedActivationJournal(
            string downloadsRoot,
            byte[] targetPointerBytes,
            byte[]? previousPointerBytes)
        {
            using JsonDocument targetDocument = JsonDocument.Parse(targetPointerBytes);
            JsonElement target = targetDocument.RootElement;
            string receiptId = target.GetProperty("activationReceiptId").GetString()!;
            string generationId = target.GetProperty("generationId").GetString()!;
            string? previousGenerationId = null;
            if (previousPointerBytes is not null)
            {
                using JsonDocument previousDocument = JsonDocument.Parse(previousPointerBytes);
                previousGenerationId = previousDocument.RootElement
                    .GetProperty("generationId")
                    .GetString();
            }

            DateTimeOffset publishedAt = DateTimeOffset.Parse(
                    target.GetProperty("publishedAt").GetString()!)
                .ToUniversalTime();
            DateTimeOffset activatedAt = DateTimeOffset.Parse(
                    target.GetProperty("activatedAt").GetString()!)
                .ToUniversalTime();
            string ShaBinding(byte[] bytes)
                => $"sha256:{Convert.ToHexStringLower(SHA256.HashData(bytes))}";
            var intent = new TestActivationIntent(
                Operation: "promotion",
                PreviousGenerationId: previousGenerationId,
                PreviousPointerSha256: previousPointerBytes is null
                    ? null
                    : ShaBinding(previousPointerBytes),
                GenerationId: generationId,
                ActivationReceiptId: receiptId,
                ReleaseVersion: target.GetProperty("releaseVersion").GetString()!,
                Channel: target.GetProperty("channel").GetString()!,
                PublishedAt: publishedAt,
                InventoryDigest: target.GetProperty("inventoryDigest").GetString()!,
                PointerSha256: ShaBinding(targetPointerBytes),
                PreparedAtUtc: activatedAt,
                PreviousPointerBase64: previousPointerBytes is null
                    ? null
                    : Convert.ToBase64String(previousPointerBytes),
                TargetPointerBase64: Convert.ToBase64String(targetPointerBytes));
            var journal = new TestActivationJournal(
                SchemaVersion: "chummer.release-shelf.activation-intent/v1",
                State: "prepared",
                Intent: intent,
                PreviousPointerBase64: previousPointerBytes is null
                    ? null
                    : Convert.ToBase64String(previousPointerBytes),
                TargetPointerBase64: Convert.ToBase64String(targetPointerBytes));
            var options = new JsonSerializerOptions(JsonSerializerDefaults.Web)
            {
                PropertyNameCaseInsensitive = true,
                WriteIndented = true
            };
            string receiptRoot = Path.Combine(
                downloadsRoot,
                ".release-shelf-activation-journal",
                receiptId);
            Directory.CreateDirectory(receiptRoot);
            byte[] intentBytes = JsonSerializer.SerializeToUtf8Bytes(journal, options);
            File.WriteAllBytes(Path.Combine(receiptRoot, "intent.json"), intentBytes);
            var outcome = new TestActivationOutcome(
                SchemaVersion: "chummer.release-shelf.activation-outcome/v1",
                State: "committed",
                ActivationReceiptId: receiptId,
                IntentSha256: ShaBinding(intentBytes),
                ResolvedAtUtc: activatedAt);
            File.WriteAllBytes(
                Path.Combine(receiptRoot, "outcome.json"),
                JsonSerializer.SerializeToUtf8Bytes(outcome, options));
        }

        private sealed record TestActivationJournal(
            string SchemaVersion,
            string State,
            TestActivationIntent Intent,
            string? PreviousPointerBase64,
            string TargetPointerBase64);

        private sealed record TestActivationIntent(
            string Operation,
            string? PreviousGenerationId,
            string? PreviousPointerSha256,
            string GenerationId,
            string ActivationReceiptId,
            string ReleaseVersion,
            string Channel,
            DateTimeOffset PublishedAt,
            string InventoryDigest,
            string PointerSha256,
            DateTimeOffset PreparedAtUtc,
            string? PreviousPointerBase64,
            string? TargetPointerBase64);

        private sealed record TestActivationOutcome(
            string SchemaVersion,
            string State,
            string ActivationReceiptId,
            string IntentSha256,
            DateTimeOffset ResolvedAtUtc);

        private sealed record GenerationMetadata(
            string Version,
            string CanonicalSha256,
            string CompatibilitySha256,
            string InventoryDigest);
    }
}
