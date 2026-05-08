using Chummer.Run.Api.Controllers;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.Services.InstallLinking;
using System.Text.Json;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class InternalReleaseBundlesControllerTests
{
    [Fact]
    public async Task UploadBundleAcceptsSignedInReleaseUploadTicket()
    {
        using ControllerFixture fixture = new();
        ReleaseUploadTicketIssueResult issued = fixture.ReleaseUploadTickets.Issue(new AuthenticatedHubSubject(
            SubjectId: "subject-archon",
            DisplayName: "Archon",
            Email: "archon@example.com",
            Roles: ["operator"],
            AccessToken: "token"));
        fixture.Controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };
        fixture.Controller.ControllerContext.HttpContext.Request.Headers.Authorization = $"Bearer {issued.Ticket}";

        ActionResult<ReleaseBundlePromotionResult> result = await fixture.Controller.UploadBundle(bundle: null, CancellationToken.None);

        ObjectResult badRequest = Assert.IsType<ObjectResult>(result.Result);
        Assert.Equal(StatusCodes.Status400BadRequest, badRequest.StatusCode);
    }

    [Fact]
    public async Task UploadSessionLifecyclePromotesBundleAndReturnsSignedInClaims()
    {
        using ControllerFixture fixture = new();
        AuthenticateController(fixture);

        OkObjectResult sessionResponse = Assert.IsType<OkObjectResult>(fixture.Controller.CreateUploadSession().Result);
        var created = Assert.IsType<InternalReleaseBundlesController.ReleaseUploadSessionCreatedResponse>(sessionResponse.Value);

        await UploadFileAsync(fixture.Controller, created.SessionId, "releases.json", "application/json", BuildCompatibilityManifest());
        await UploadFileAsync(fixture.Controller, created.SessionId, "RELEASE_CHANNEL.generated.json", "application/json", BuildCanonicalManifest());
        await UploadFileAsync(fixture.Controller, created.SessionId, "release-evidence/public-promotion.json", "application/json", BuildPromotionEvidence());
        await UploadFileAsync(fixture.Controller, created.SessionId, "files/chummer-avalonia-osx-arm64-installer.dmg", "application/octet-stream", "mac-live"u8.ToArray());
        await UploadFileAsync(fixture.Controller, created.SessionId, "startup-smoke/startup-smoke-avalonia-macos-arm64.receipt.json", "application/json", BuildStartupSmokeReceipt());

        ActionResult<ReleaseBundlePromotionResult> completeResult = await fixture.Controller.CompleteUploadSession(created.SessionId, CancellationToken.None);
        OkObjectResult ok = Assert.IsType<OkObjectResult>(completeResult.Result);
        ReleaseBundlePromotionResult promoted = Assert.IsType<ReleaseBundlePromotionResult>(ok.Value);
        Assert.Contains("avalonia-osx-arm64-dmg", promoted.PromotedArtifactIds);
        Assert.NotNull(promoted.SignedInInstallClaims);
        Assert.NotEmpty(promoted.SignedInInstallClaims!);
    }

    [Fact]
    public async Task UploadSessionFileRejectsExpiredSession()
    {
        using ControllerFixture fixture = new();
        AuthenticateController(fixture);

        OkObjectResult sessionResponse = Assert.IsType<OkObjectResult>(fixture.Controller.CreateUploadSession().Result);
        var created = Assert.IsType<InternalReleaseBundlesController.ReleaseUploadSessionCreatedResponse>(sessionResponse.Value);
        fixture.WriteSessionMetadata(new ReleaseUploadSession(
            created.SessionId,
            DateTimeOffset.UtcNow.AddMinutes(-1),
            Path.Combine(fixture.SessionRoot, created.SessionId, "bundle")));

        FormFile formFile = BuildTextFormFile("releases.json", "application/json", "{}");
        ActionResult<InternalReleaseBundlesController.ReleaseUploadFileStoredResponse> response = await fixture.Controller.UploadSessionFile(
            created.SessionId,
            formFile,
            "releases.json",
            CancellationToken.None);

        ObjectResult badRequest = Assert.IsType<ObjectResult>(response.Result);
        ProblemDetails? problem = Assert.IsType<ProblemDetails>(badRequest.Value);
        Assert.Equal(StatusCodes.Status400BadRequest, badRequest.StatusCode);
        Assert.Equal("Upload session file rejected", problem.Title);
        Assert.Contains("upload session has expired", problem.Detail ?? string.Empty, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task UploadSessionFileRejectsInvalidSessionId()
    {
        using ControllerFixture fixture = new();
        AuthenticateController(fixture);

        FormFile formFile = BuildTextFormFile("releases.json", "application/json", "{}{");
        ActionResult<InternalReleaseBundlesController.ReleaseUploadFileStoredResponse> response = await fixture.Controller.UploadSessionFile(
            "not-a-guid",
            formFile,
            "releases.json",
            CancellationToken.None);

        ObjectResult badRequest = Assert.IsType<ObjectResult>(response.Result);
        ProblemDetails? problem = Assert.IsType<ProblemDetails>(badRequest.Value);
        Assert.Equal(StatusCodes.Status400BadRequest, badRequest.StatusCode);
        Assert.Equal("Upload session file rejected", problem.Title);
        Assert.Contains("sessionId must be a valid GUID", problem.Detail ?? string.Empty, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task UploadSessionChunkRejectsInvalidSessionId()
    {
        using ControllerFixture fixture = new();
        AuthenticateController(fixture);

        FormFile chunk = BuildTextFormFile("chunk.bin", "application/octet-stream", "chunk");
        ActionResult<InternalReleaseBundlesController.ReleaseUploadChunkStoredResponse> response = await fixture.Controller.UploadSessionChunk(
            "bad-session-id",
            chunk,
            "files/chummer-avalonia-win-x64.exe",
            chunkIndex: 0,
            totalChunks: 1,
            CancellationToken.None);

        ObjectResult badRequest = Assert.IsType<ObjectResult>(response.Result);
        ProblemDetails? problem = Assert.IsType<ProblemDetails>(badRequest.Value);
        Assert.Equal(StatusCodes.Status400BadRequest, badRequest.StatusCode);
        Assert.Equal("Upload session chunk rejected", problem.Title);
        Assert.Contains("sessionId must be a valid GUID", problem.Detail ?? string.Empty, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task CompleteUploadSessionRejectsInvalidSessionId()
    {
        using ControllerFixture fixture = new();
        AuthenticateController(fixture);

        ActionResult<ReleaseBundlePromotionResult> response = await fixture.Controller.CompleteUploadSession(
            "0x-not-a-guid",
            CancellationToken.None);

        ObjectResult badRequest = Assert.IsType<ObjectResult>(response.Result);
        ProblemDetails? problem = Assert.IsType<ProblemDetails>(badRequest.Value);
        Assert.Equal(StatusCodes.Status400BadRequest, badRequest.StatusCode);
        Assert.Equal("Upload session promotion rejected", problem.Title);
        Assert.Contains("sessionId must be a valid GUID", problem.Detail ?? string.Empty, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task UploadSessionChunkRejectsExpiredSession()
    {
        using ControllerFixture fixture = new();
        AuthenticateController(fixture);

        OkObjectResult sessionResponse = Assert.IsType<OkObjectResult>(fixture.Controller.CreateUploadSession().Result);
        var created = Assert.IsType<InternalReleaseBundlesController.ReleaseUploadSessionCreatedResponse>(sessionResponse.Value);
        fixture.WriteSessionMetadata(new ReleaseUploadSession(
            created.SessionId,
            DateTimeOffset.UtcNow.AddMinutes(-1),
            Path.Combine(fixture.SessionRoot, created.SessionId, "bundle")));

        FormFile formFile = BuildTextFormFile("chunk.bin", "application/octet-stream", "chunk");
        ActionResult<InternalReleaseBundlesController.ReleaseUploadChunkStoredResponse> response = await fixture.Controller.UploadSessionChunk(
            created.SessionId,
            formFile,
            "files/chummer-avalonia-osx-arm64-installer.dmg",
            chunkIndex: 0,
            totalChunks: 1,
            CancellationToken.None);

        ObjectResult badRequest = Assert.IsType<ObjectResult>(response.Result);
        ProblemDetails? problem = Assert.IsType<ProblemDetails>(badRequest.Value);
        Assert.Equal(StatusCodes.Status400BadRequest, badRequest.StatusCode);
        Assert.Equal("Upload session chunk rejected", problem.Title);
        Assert.Contains("upload session has expired", problem.Detail ?? string.Empty, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task CompleteUploadSessionRejectsExpiredSession()
    {
        using ControllerFixture fixture = new();
        AuthenticateController(fixture);

        OkObjectResult sessionResponse = Assert.IsType<OkObjectResult>(fixture.Controller.CreateUploadSession().Result);
        var created = Assert.IsType<InternalReleaseBundlesController.ReleaseUploadSessionCreatedResponse>(sessionResponse.Value);
        fixture.WriteSessionMetadata(new ReleaseUploadSession(
            created.SessionId,
            DateTimeOffset.UtcNow.AddMinutes(-1),
            Path.Combine(fixture.SessionRoot, created.SessionId, "bundle")));

        ActionResult<ReleaseBundlePromotionResult> response = await fixture.Controller.CompleteUploadSession(
            created.SessionId,
            CancellationToken.None);

        ObjectResult badRequest = Assert.IsType<ObjectResult>(response.Result);
        ProblemDetails? problem = Assert.IsType<ProblemDetails>(badRequest.Value);
        Assert.Equal(StatusCodes.Status400BadRequest, badRequest.StatusCode);
        Assert.Equal("Upload session promotion rejected", problem.Title);
        Assert.Contains("upload session has expired", problem.Detail ?? string.Empty, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task UploadSessionRejectsTamperedSessionMetadata()
    {
        using ControllerFixture fixture = new();
        AuthenticateController(fixture);

        OkObjectResult sessionResponse = Assert.IsType<OkObjectResult>(fixture.Controller.CreateUploadSession().Result);
        var created = Assert.IsType<InternalReleaseBundlesController.ReleaseUploadSessionCreatedResponse>(sessionResponse.Value);
        string tamperedSessionId = Guid.NewGuid().ToString("N");
        fixture.WriteSessionMetadata(created.SessionId, new ReleaseUploadSession(
            tamperedSessionId,
            DateTimeOffset.UtcNow.AddHours(6),
            Path.Combine(fixture.SessionRoot, created.SessionId, "bundle")));

        FormFile formFile = BuildTextFormFile("releases.json", "application/json", "{}");
        ActionResult<InternalReleaseBundlesController.ReleaseUploadFileStoredResponse> response = await fixture.Controller.UploadSessionFile(
            created.SessionId,
            formFile,
            "releases.json",
            CancellationToken.None);

        ObjectResult badRequest = Assert.IsType<ObjectResult>(response.Result);
        ProblemDetails? problem = Assert.IsType<ProblemDetails>(badRequest.Value);
        Assert.Equal(StatusCodes.Status400BadRequest, badRequest.StatusCode);
        Assert.Equal("Upload session file rejected", problem.Title);
        Assert.Contains("metadata is invalid", problem.Detail ?? string.Empty, StringComparison.OrdinalIgnoreCase);
    }

    private static async Task UploadFileAsync(
        InternalReleaseBundlesController controller,
        string sessionId,
        string relativePath,
        string contentType,
        byte[] bytes)
    {
        FormFile formFile = new(new MemoryStream(bytes), 0, bytes.Length, "file", Path.GetFileName(relativePath))
        {
            Headers = new HeaderDictionary(),
            ContentType = contentType
        };
        ActionResult<InternalReleaseBundlesController.ReleaseUploadFileStoredResponse> response = await controller.UploadSessionFile(
            sessionId,
            formFile,
            relativePath,
            CancellationToken.None);
        Assert.IsType<OkObjectResult>(response.Result);
    }

    private static FormFile BuildTextFormFile(string fileName, string contentType, string text)
    {
        return BuildByteFormFile(fileName, contentType, System.Text.Encoding.UTF8.GetBytes(text));
    }

    private static FormFile BuildByteFormFile(string fileName, string contentType, byte[] bytes)
    {
        return new FormFile(new MemoryStream(bytes), 0, bytes.Length, "file", fileName)
        {
            Headers = new HeaderDictionary(),
            ContentType = contentType
        };
    }

    private static void AuthenticateController(ControllerFixture fixture)
    {
        ReleaseUploadTicketIssueResult issued = fixture.ReleaseUploadTickets.Issue(new AuthenticatedHubSubject(
            SubjectId: "subject-archon",
            DisplayName: "Archon",
            Email: "archon@example.com",
            Roles: ["operator"],
            AccessToken: "token"));

        fixture.Controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };
        fixture.Controller.ControllerContext.HttpContext.Request.Scheme = "https";
        fixture.Controller.ControllerContext.HttpContext.Request.Host = new HostString("chummer.run");
        fixture.Controller.ControllerContext.HttpContext.Request.Headers.Authorization = $"Bearer {issued.Ticket}";
    }

    private static byte[] BuildCompatibilityManifest()
        => System.Text.Encoding.UTF8.GetBytes("""
{
  "version": "run-test",
  "channel": "preview",
  "publishedAt": "2026-04-02T06:00:00Z",
  "downloads": [
    {
      "id": "avalonia-osx-arm64-dmg",
      "platform": "Avalonia Desktop macOS arm64",
      "url": "/downloads/files/chummer-avalonia-osx-arm64-installer.dmg",
      "sha256": "6f63f1170506eaca21ee53bf90415ee7ed4f40937c505f140137259e27a65bab",
      "sizeBytes": 8,
      "head": "avalonia",
      "platformId": "macos-arm64",
      "arch": "arm64",
      "kind": "dmg",
      "fileName": "chummer-avalonia-osx-arm64-installer.dmg",
      "installAccessClass": "account_required"
    }
  ]
}
""");

    private static byte[] BuildCanonicalManifest()
        => System.Text.Encoding.UTF8.GetBytes("""
{
  "schemaVersion": 1,
  "product": "chummer",
  "channelId": "preview",
  "version": "run-test",
  "publishedAt": "2026-04-02T06:00:00Z",
  "status": "published",
  "artifacts": [
    {
      "artifactId": "avalonia-osx-arm64-dmg",
      "head": "avalonia",
      "platform": "macos",
      "arch": "arm64",
      "kind": "dmg",
      "fileName": "chummer-avalonia-osx-arm64-installer.dmg",
      "downloadUrl": "/downloads/files/chummer-avalonia-osx-arm64-installer.dmg",
      "sha256": "6f63f1170506eaca21ee53bf90415ee7ed4f40937c505f140137259e27a65bab",
      "sizeBytes": 8,
      "platformLabel": "Avalonia Desktop macOS ARM64"
    }
  ]
}
""");

    private static byte[] BuildPromotionEvidence()
        => System.Text.Encoding.UTF8.GetBytes("""
{
  "contractName": "chummer.run.desktop_release_publication",
  "generatedAt": "2026-04-02T06:00:00Z",
  "artifacts": [
    {
      "artifactId": "avalonia-osx-arm64-dmg",
      "fileName": "chummer-avalonia-osx-arm64-installer.dmg",
      "platform": "macos",
      "promotionStatus": "pass",
      "startupSmokeStatus": "pass",
      "signingStatus": "skipped_preview",
      "notarizationStatus": "skipped_preview"
    }
  ]
}
""");

    private static byte[] BuildStartupSmokeReceipt()
        => System.Text.Encoding.UTF8.GetBytes("""
{
  "headId": "avalonia",
  "platform": "macos",
  "arch": "arm64",
  "artifactDigest": "sha256:6f63f1170506eaca21ee53bf90415ee7ed4f40937c505f140137259e27a65bab"
}
""");

    private sealed class ControllerFixture : IDisposable
    {
        private readonly string _root;

        public ControllerFixture()
        {
            _root = Path.Combine(Path.GetTempPath(), "internal-release-bundles-controller-tests", Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(_root);

            Configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_DOWNLOADS_SOURCE_ROOT"] = Path.Combine(_root, "downloads"),
                    ["GOOGLE_OIDC_REDIRECT_URI"] = "https://chummer.run/auth/google/callback",
                    ["CHUMMER_PUBLIC_CANON_ROOT"] = Path.Combine(_root, "canon"),
                    ["CHUMMER_COMMUNITY_STORE_PATH"] = Path.Combine(_root, "community.json"),
                    ["CHUMMER_INSTALL_LINKING_STORE_PATH"] = Path.Combine(_root, "install-linking.json")
                })
                .Build();
            Configuration["CHUMMER_RELEASE_UPLOAD_SESSION_ROOT"] = Path.Combine(_root, "sessions");

            IDataProtectionProvider dataProtectionProvider = DataProtectionProvider.Create(new DirectoryInfo(Path.Combine(_root, "keys")));
            ReleaseUploadTickets = new ReleaseUploadTicketService(dataProtectionProvider, Configuration);
            var releasePromotion = new ReleaseBundlePromotionService(Configuration, NullLogger<ReleaseBundlePromotionService>.Instance);
            var uploadSessions = new ReleaseBundleUploadSessionService(Configuration, NullLogger<ReleaseBundleUploadSessionService>.Instance);
            var manifestService = new PublicReleaseManifestService(Configuration);
            var accounts = new AccountService(new CommunityStore(Configuration, NullLogger<CommunityStore>.Instance));
            var installLinking = new InstallLinkingService(new InstallLinkingStore(Configuration, NullLogger<InstallLinkingStore>.Instance), Configuration);
            Controller = new InternalReleaseBundlesController(
                releasePromotion,
                uploadSessions,
                Configuration,
                ReleaseUploadTickets,
                manifestService,
                accounts,
                installLinking);
        }

        public IConfiguration Configuration { get; }

        public ReleaseUploadTicketService ReleaseUploadTickets { get; }

        public InternalReleaseBundlesController Controller { get; }

        public string SessionRoot => Path.Combine(_root, "sessions");

        public void WriteSessionMetadata(ReleaseUploadSession session)
        {
            string path = Path.Combine(SessionRoot, session.SessionId, "session.json");
            Directory.CreateDirectory(Path.GetDirectoryName(path)!);
            File.WriteAllText(path, JsonSerializer.Serialize(session));
        }

        public void WriteSessionMetadata(string storageSessionId, ReleaseUploadSession session)
        {
            string path = Path.Combine(SessionRoot, storageSessionId, "session.json");
            Directory.CreateDirectory(Path.GetDirectoryName(path)!);
            File.WriteAllText(path, JsonSerializer.Serialize(session));
        }

        public void Dispose()
        {
            if (Directory.Exists(_root))
            {
                Directory.Delete(_root, recursive: true);
            }
        }
    }
}
