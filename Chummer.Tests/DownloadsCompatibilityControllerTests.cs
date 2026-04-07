using Chummer.Run.Api.Controllers;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.Services.InstallLinking;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class DownloadsCompatibilityControllerTests
{
    [Fact]
    public void CanonicalReleaseManifestServesRegistryProjection()
    {
        using Fixture fixture = new();

        IActionResult result = fixture.Controller.CanonicalReleaseManifest();

        var file = Assert.IsType<PhysicalFileResult>(result);
        Assert.EndsWith("RELEASE_CHANNEL.generated.json", file.FileName, StringComparison.Ordinal);
        Assert.Equal("application/json; charset=utf-8", file.ContentType);
    }

    [Fact]
    public async Task AccountRequiredMacArtifactDownloadAcceptsClaimCodeWithoutBrowserSession()
    {
        using Fixture fixture = new();
        var manifest = fixture.ManifestService.LoadManifest();
        var artifact = Assert.Single(manifest.Downloads, item => string.Equals(item.Id, "avalonia-osx-x64-installer", StringComparison.OrdinalIgnoreCase));
        var dispatch = fixture.InstallLinking.IssueDownload(manifest, artifact, "user-archon", "subject-archon");
        Assert.NotNull(dispatch.ClaimTicket);

        fixture.Controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };
        fixture.Controller.ControllerContext.HttpContext.Request.QueryString = new QueryString(
            $"?claimCode={Uri.EscapeDataString(dispatch.ClaimTicket!.ClaimCode)}");

        IActionResult result = await fixture.Controller.DownloadResolvedArtifactFile("avalonia-osx-x64-installer", CancellationToken.None);

        var file = Assert.IsType<PhysicalFileResult>(result);
        Assert.Equal("chummer-avalonia-osx-x64-installer.dmg", file.FileDownloadName);
        Assert.Equal("private, no-store", fixture.Controller.ControllerContext.HttpContext.Response.Headers.CacheControl.ToString());
    }

    [Fact]
    public async Task AccountRequiredMacArtifactDownloadAcceptsBootstrapTicketWithoutBrowserSession()
    {
        using Fixture fixture = new();
        var ticket = fixture.InstallBootstrapTickets.Issue(
            "avalonia-osx-x64-installer",
            ["avalonia-osx-x64-installer"],
            "user-archon",
            "subject-archon");

        fixture.Controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };
        fixture.Controller.ControllerContext.HttpContext.Request.QueryString = new QueryString(
            $"?ticket={Uri.EscapeDataString(ticket.Ticket)}");

        IActionResult result = await fixture.Controller.DownloadResolvedArtifactFile("avalonia-osx-x64-installer", CancellationToken.None);

        var file = Assert.IsType<PhysicalFileResult>(result);
        Assert.Equal("chummer-avalonia-osx-x64-installer.dmg", file.FileDownloadName);
        Assert.Equal("private, no-store", fixture.Controller.ControllerContext.HttpContext.Response.Headers.CacheControl.ToString());
    }

    [Fact]
    public async Task AccountRequiredMacArtifactStillRedirectsToLoginWithoutClaimCode()
    {
        using Fixture fixture = new();
        fixture.Controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };

        IActionResult result = await fixture.Controller.DownloadResolvedArtifactFile("avalonia-osx-x64-installer", CancellationToken.None);

        var redirect = Assert.IsType<RedirectResult>(result);
        Assert.StartsWith("/login?next=", redirect.Url, StringComparison.Ordinal);
        Assert.Contains("%2Fdownloads%2Finstall%2Favalonia-osx-x64-installer", redirect.Url, StringComparison.Ordinal);
    }

    [Fact]
    public async Task AccountRequiredWindowsArtifactStillRedirectsToLoginWithoutClaimCode()
    {
        using Fixture fixture = new();
        fixture.Controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };

        IActionResult result = await fixture.Controller.DownloadFile("chummer-avalonia-win-x64-installer.exe", CancellationToken.None);

        var redirect = Assert.IsType<RedirectResult>(result);
        Assert.StartsWith("/login?next=", redirect.Url, StringComparison.Ordinal);
        Assert.Contains("%2Fdownloads%2Finstall%2Favalonia-win-x64-installer", redirect.Url, StringComparison.Ordinal);
    }

    [Fact]
    public async Task AccountRequiredMacArtifactRejectsInvalidClaimCodeWithoutRedirectingToLogin()
    {
        using Fixture fixture = new();
        fixture.Controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };
        fixture.Controller.ControllerContext.HttpContext.Request.QueryString = new QueryString("?claimCode=BAD-CODE");

        IActionResult result = await fixture.Controller.DownloadResolvedArtifactFile("avalonia-osx-x64-installer", CancellationToken.None);

        var unauthorized = Assert.IsType<UnauthorizedObjectResult>(result);
        Assert.Equal(StatusCodes.Status401Unauthorized, unauthorized.StatusCode);
        Assert.Equal("private, no-store", fixture.Controller.ControllerContext.HttpContext.Response.Headers.CacheControl.ToString());
    }

    [Fact]
    public async Task AccountRequiredMacArtifactRejectsInvalidBootstrapTicketWithoutRedirectingToLogin()
    {
        using Fixture fixture = new();
        fixture.Controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };
        fixture.Controller.ControllerContext.HttpContext.Request.QueryString = new QueryString("?ticket=BAD-TICKET");

        IActionResult result = await fixture.Controller.DownloadResolvedArtifactFile("avalonia-osx-x64-installer", CancellationToken.None);

        var unauthorized = Assert.IsType<UnauthorizedObjectResult>(result);
        Assert.Equal(StatusCodes.Status401Unauthorized, unauthorized.StatusCode);
        Assert.Equal("private, no-store", fixture.Controller.ControllerContext.HttpContext.Response.Headers.CacheControl.ToString());
    }

    [Fact]
    public async Task DirectFileRouteDoesNotExposeWithheldMacArtifact()
    {
        using Fixture fixture = new();

        IActionResult result = await fixture.Controller.DownloadFile("chummer-avalonia-osx-x64-installer.dmg", CancellationToken.None);

        Assert.IsType<NotFoundResult>(result);
    }

    private sealed class Fixture : IDisposable
    {
        private readonly string _root;

        public Fixture()
        {
            _root = Path.Combine(Path.GetTempPath(), "downloads-compatibility-controller-tests", Guid.NewGuid().ToString("N"));
            string downloadsRoot = Path.Combine(_root, "downloads");
            string filesRoot = Path.Combine(downloadsRoot, "files");
            Directory.CreateDirectory(filesRoot);
            File.WriteAllBytes(Path.Combine(filesRoot, "chummer-avalonia-osx-x64-installer.dmg"), "mac-preview"u8.ToArray());
            File.WriteAllBytes(Path.Combine(filesRoot, "chummer-avalonia-win-x64-installer.exe"), "win-preview"u8.ToArray());
            File.WriteAllText(
                Path.Combine(downloadsRoot, "releases.json"),
                """
                {
                  "version": "run-test",
                  "channel": "preview",
                  "publishedAt": "2026-04-02T16:14:30Z",
                  "proofStatus": "passed",
                  "proofRoutes": [
                    "/downloads/install/avalonia-osx-x64-installer",
                    "/downloads/file/avalonia-osx-x64-installer",
                    "/downloads/install/avalonia-win-x64-installer"
                  ],
                  "downloads": [
                    {
                      "id": "avalonia-osx-x64-installer",
                      "platform": "Avalonia Desktop macOS X64 Installer",
                      "url": "/downloads/files/chummer-avalonia-osx-x64-installer.dmg",
                      "sha256": "71cea7987b5323078baed5c104ca82ef80060b249f3fa8401ddf42d0e6ed8c39",
                      "sizeBytes": 51887995,
                      "head": "avalonia",
                      "platformId": "macOS",
                      "arch": "x64",
                      "kind": "dmg",
                      "fileName": "chummer-avalonia-osx-x64-installer.dmg",
                      "installAccessClass": "account_required"
                    },
                    {
                      "id": "avalonia-win-x64-installer",
                      "platform": "Avalonia Desktop Windows X64 Installer",
                      "url": "/downloads/files/chummer-avalonia-win-x64-installer.exe",
                      "sha256": "34f6cb5006019d6c8e19d55c32302efea6aaed7cd63f3770aee7f087f0ee4bf9",
                      "sizeBytes": 51887995,
                      "head": "avalonia",
                      "platformId": "win-x64",
                      "arch": "x64",
                      "kind": "installer",
                      "fileName": "chummer-avalonia-win-x64-installer.exe",
                      "installAccessClass": "account_required"
                    }
                  ]
                }
                """);
            File.WriteAllText(
                Path.Combine(downloadsRoot, "RELEASE_CHANNEL.generated.json"),
                """
                {
                  "product": "chummer",
                  "channelId": "preview",
                  "version": "run-test",
                  "publishedAt": "2026-04-02T16:14:30Z",
                  "status": "published",
                  "artifacts": [
                    {
                      "artifactId": "avalonia-osx-x64-installer",
                      "head": "avalonia",
                      "platform": "macos",
                      "arch": "x64",
                      "kind": "dmg",
                      "platformLabel": "Avalonia Desktop macOS X64 Installer",
                      "fileName": "chummer-avalonia-osx-x64-installer.dmg",
                      "downloadUrl": "/downloads/files/chummer-avalonia-osx-x64-installer.dmg",
                      "sha256": "71cea7987b5323078baed5c104ca82ef80060b249f3fa8401ddf42d0e6ed8c39",
                      "sizeBytes": 51887995,
                      "installAccessClass": "account_required"
                    },
                    {
                      "artifactId": "avalonia-win-x64-installer",
                      "head": "avalonia",
                      "platform": "windows",
                      "arch": "x64",
                      "kind": "installer",
                      "platformLabel": "Avalonia Desktop Windows X64 Installer",
                      "fileName": "chummer-avalonia-win-x64-installer.exe",
                      "downloadUrl": "/downloads/files/chummer-avalonia-win-x64-installer.exe",
                      "sha256": "34f6cb5006019d6c8e19d55c32302efea6aaed7cd63f3770aee7f087f0ee4bf9",
                      "sizeBytes": 51887995,
                      "installAccessClass": "account_required"
                    }
                  ]
                }
                """);

            Configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_DOWNLOADS_SOURCE_ROOT"] = downloadsRoot,
                    ["CHUMMER_PUBLIC_CANON_ROOT"] = RepoPaths.Root,
                    ["CHUMMER_INSTALL_LINKING_STORE_PATH"] = Path.Combine(_root, "install-linking.json"),
                    ["IDENTITY_SERVICE_BASE_URL"] = "http://127.0.0.1:9"
                })
                .Build();

            ManifestService = new PublicReleaseManifestService(Configuration);
            ReleaseSelection = new ReleaseSelectionService(new PublicCanonFileLoader(Configuration));
            InstallBootstrapTickets = new InstallBootstrapTicketService(
                Microsoft.AspNetCore.DataProtection.DataProtectionProvider.Create(new DirectoryInfo(Path.Combine(_root, "keys"))),
                Configuration);
            InstallLinking = new InstallLinkingService(new InstallLinkingStore(Configuration, NullLogger<InstallLinkingStore>.Instance));
            var identityClient = new HubIdentityClient(new HttpClient(), Configuration, NullLogger<HubIdentityClient>.Instance);
            Controller = new DownloadsCompatibilityController(
                ManifestService,
                ReleaseSelection,
                InstallLinking,
                InstallBootstrapTickets,
                identityClient,
                NullLogger<DownloadsCompatibilityController>.Instance);
        }

        public IConfiguration Configuration { get; }

        public PublicReleaseManifestService ManifestService { get; }

        public ReleaseSelectionService ReleaseSelection { get; }

        public InstallBootstrapTicketService InstallBootstrapTickets { get; }

        public InstallLinkingService InstallLinking { get; }

        public DownloadsCompatibilityController Controller { get; }

        public void Dispose()
        {
            if (Directory.Exists(_root))
            {
                Directory.Delete(_root, recursive: true);
            }
        }
    }
}
