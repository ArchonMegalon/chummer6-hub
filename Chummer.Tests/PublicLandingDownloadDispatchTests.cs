using System.Text;
using Chummer.Run.Api.Controllers;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.InstallLinking;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.Routing;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class PublicLandingDownloadDispatchTests
{
    [Fact]
    public void DownloadDispatchPage_Advertises_Head_And_Get_For_Probe_Safe_Install_Handoff()
    {
        var method = typeof(PublicLandingController).GetMethod(nameof(PublicLandingController.DownloadDispatchPage));
        Assert.NotNull(method);

        var routes = method!
            .GetCustomAttributes(typeof(HttpMethodAttribute), inherit: true)
            .Cast<HttpMethodAttribute>()
            .ToArray();

        Assert.Contains(routes, route =>
            string.Equals(route.Template, "/downloads/install/{artifactId}", StringComparison.Ordinal)
            && route.HttpMethods.Contains("GET", StringComparer.OrdinalIgnoreCase));
        Assert.Contains(routes, route =>
            string.Equals(route.Template, "/downloads/install/{artifactId}", StringComparison.Ordinal)
            && route.HttpMethods.Contains("HEAD", StringComparer.OrdinalIgnoreCase));
    }

    [Fact]
    public async Task BootstrapScriptAcceptsInstallTicketWithoutBrowserSession()
    {
        using Fixture fixture = new();
        var manifest = fixture.ManifestService.LoadManifest();
        var artifact = Assert.Single(manifest.Downloads, item => string.Equals(item.Id, "avalonia-osx-arm64-installer", StringComparison.OrdinalIgnoreCase));
        var ticket = fixture.InstallBootstrapTickets.Issue(
            artifact.Id,
            ["avalonia-osx-arm64-installer", "blazor-desktop-osx-arm64-installer", "avalonia-osx-x64-installer"],
            "user-archon",
            "subject-archon");

        fixture.Controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };
        fixture.Controller.ControllerContext.HttpContext.Request.Scheme = "https";
        fixture.Controller.ControllerContext.HttpContext.Request.Host = new HostString("chummer.run");
        fixture.Controller.ControllerContext.HttpContext.Request.QueryString = new QueryString(
            $"?ticket={Uri.EscapeDataString(ticket.Ticket)}");

        IActionResult result = await fixture.Controller.DownloadDispatchBootstrapScript("avalonia-osx-arm64-installer", CancellationToken.None);

        var file = Assert.IsType<FileContentResult>(result);
        Assert.Equal("Chummer Setup.command", file.FileDownloadName);
        string script = Encoding.UTF8.GetString(file.FileContents);
        Assert.Contains("https://chummer.run/downloads/file/avalonia-osx-arm64-installer", script, StringComparison.Ordinal);
        Assert.Contains("https://chummer.run/downloads/file/blazor-desktop-osx-arm64-installer", script, StringComparison.Ordinal);
        Assert.Contains("https://chummer.run/downloads/file/avalonia-osx-x64-installer", script, StringComparison.Ordinal);
        Assert.Contains("CLAIM_CODES", script, StringComparison.Ordinal);
        Assert.Contains("build_claim_download_url()", script, StringComparison.Ordinal);
        Assert.Contains("HEAD_IDS", script, StringComparison.Ordinal);
        Assert.Contains("Chummer Avalonia (Intel)", script, StringComparison.Ordinal);
        Assert.Contains("wait_for_claim_success", script, StringComparison.Ordinal);
        Assert.Contains("Confirmed linked installs", script, StringComparison.Ordinal);
        Assert.Contains("claimCode=", script, StringComparison.Ordinal);
        Assert.Equal("private, no-store", fixture.Controller.ControllerContext.HttpContext.Response.Headers.CacheControl.ToString());
    }

    [Fact]
    public async Task PersonalizedMacBootstrapScriptConsumesSingleUseLinkAndEmbedsClaimCodes()
    {
        using Fixture fixture = new();
        var issue = fixture.PersonalizedInstallScripts.IssueMacScript(
            "avalonia-osx-arm64-installer",
            ["avalonia-osx-arm64-installer", "blazor-desktop-osx-arm64-installer", "avalonia-osx-x64-installer"],
            "user-archon",
            "subject-archon");

        fixture.Controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };
        fixture.Controller.ControllerContext.HttpContext.Request.Scheme = "https";
        fixture.Controller.ControllerContext.HttpContext.Request.Host = new HostString("chummer.run");

        IActionResult first = fixture.Controller.DownloadDispatchPersonalizedMacBootstrapScript(issue.ScriptId);

        var file = Assert.IsType<FileContentResult>(first);
        string script = Encoding.UTF8.GetString(file.FileContents);
        Assert.Contains("CLAIM_CODES", script, StringComparison.Ordinal);
        Assert.Contains("build_claim_download_url()", script, StringComparison.Ordinal);
        Assert.Contains("https://chummer.run/downloads/file/avalonia-osx-arm64-installer", script, StringComparison.Ordinal);
        Assert.Contains("claimCode=", script, StringComparison.Ordinal);
        Assert.Equal("private, no-store", fixture.Controller.ControllerContext.HttpContext.Response.Headers.CacheControl.ToString());

        IActionResult second = fixture.Controller.DownloadDispatchPersonalizedMacBootstrapScript(issue.ScriptId);

        var gone = Assert.IsType<ObjectResult>(second);
        Assert.Equal(StatusCodes.Status410Gone, gone.StatusCode);
    }

    [Fact]
    public void PersonalizedMacBootstrapScriptReturnsStoredRenderedScriptWhenPresent()
    {
        using Fixture fixture = new();
        const string renderedScript = "#!/usr/bin/env bash\nprintf 'ok\\n'";
        var issue = fixture.PersonalizedInstallScripts.IssueMacScript(
            "avalonia-osx-arm64-installer",
            ["avalonia-osx-arm64-installer"],
            "user-archon",
            "subject-archon",
            renderedScript);

        fixture.Controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };
        fixture.Controller.ControllerContext.HttpContext.Request.Scheme = "https";
        fixture.Controller.ControllerContext.HttpContext.Request.Host = new HostString("chummer.run");

        IActionResult result = fixture.Controller.DownloadDispatchPersonalizedMacBootstrapScript(issue.ScriptId);

        var file = Assert.IsType<FileContentResult>(result);
        Assert.Equal(renderedScript, Encoding.UTF8.GetString(file.FileContents));
    }

    [Fact]
    public async Task BootstrapScriptRejectsInvalidInstallTicketWithoutRedirectingToLogin()
    {
        using Fixture fixture = new();
        fixture.Controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };
        fixture.Controller.ControllerContext.HttpContext.Request.QueryString = new QueryString("?ticket=BAD-TICKET");

        IActionResult result = await fixture.Controller.DownloadDispatchBootstrapScript("avalonia-osx-arm64-installer", CancellationToken.None);

        var unauthorized = Assert.IsType<UnauthorizedObjectResult>(result);
        Assert.Equal(StatusCodes.Status401Unauthorized, unauthorized.StatusCode);
        Assert.Equal("private, no-store", fixture.Controller.ControllerContext.HttpContext.Response.Headers.CacheControl.ToString());
    }

    [Fact]
    public async Task WindowsBootstrapScriptAcceptsInstallTicketWithoutBrowserSession()
    {
        using Fixture fixture = new();
        var manifest = fixture.ReleaseSelection.ApplyAccessPolicy(fixture.ManifestService.LoadManifest());
        var artifact = Assert.Single(manifest.Downloads, item => string.Equals(item.Id, "avalonia-win-x64-installer", StringComparison.OrdinalIgnoreCase));
        var ticket = fixture.InstallBootstrapTickets.Issue(
            artifact.Id,
            ["avalonia-win-x64-installer", "blazor-desktop-win-x64-installer"],
            "user-archon",
            "subject-archon");

        fixture.Controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };
        fixture.Controller.ControllerContext.HttpContext.Request.Scheme = "https";
        fixture.Controller.ControllerContext.HttpContext.Request.Host = new HostString("chummer.run");
        fixture.Controller.ControllerContext.HttpContext.Request.QueryString = new QueryString($"?ticket={Uri.EscapeDataString(ticket.Ticket)}");

        IActionResult result = await fixture.Controller.DownloadDispatchWindowsBootstrapScript("avalonia-win-x64-installer", CancellationToken.None);

        var file = Assert.IsType<FileContentResult>(result);
        Assert.Equal("Chummer Setup.ps1", file.FileDownloadName);
        string script = Encoding.UTF8.GetString(file.FileContents);
        Assert.Contains("blazor-desktop-win-x64-installer", script, StringComparison.Ordinal);
        Assert.Contains($"\"ClaimUrl\":\"https://chummer.run/downloads/install/avalonia-win-x64-installer/continue.json?ticket={Uri.EscapeDataString(ticket.Ticket)}\"", script, StringComparison.Ordinal);
        Assert.Contains("--bootstrap-install", script, StringComparison.Ordinal);
        Assert.Contains("ConvertFrom-Json", script, StringComparison.Ordinal);
        Assert.Contains("Confirmed linked installs", script, StringComparison.Ordinal);
        Assert.DoesNotContain("claimCode=", script, StringComparison.Ordinal);
        Assert.Equal("private, no-store", fixture.Controller.ControllerContext.HttpContext.Response.Headers.CacheControl.ToString());
    }

    [Fact]
    public async Task LinuxBootstrapScriptAcceptsInstallTicketWithoutBrowserSession()
    {
        using Fixture fixture = new();
        var manifest = fixture.ReleaseSelection.ApplyAccessPolicy(fixture.ManifestService.LoadManifest());
        var artifact = Assert.Single(manifest.Downloads, item => string.Equals(item.Id, "avalonia-linux-x64-installer", StringComparison.OrdinalIgnoreCase));
        var ticket = fixture.InstallBootstrapTickets.Issue(
            artifact.Id,
            ["avalonia-linux-x64-installer", "blazor-desktop-linux-x64-installer"],
            "user-archon",
            "subject-archon");

        fixture.Controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };
        fixture.Controller.ControllerContext.HttpContext.Request.Scheme = "https";
        fixture.Controller.ControllerContext.HttpContext.Request.Host = new HostString("chummer.run");
        fixture.Controller.ControllerContext.HttpContext.Request.QueryString = new QueryString($"?ticket={Uri.EscapeDataString(ticket.Ticket)}");

        IActionResult result = await fixture.Controller.DownloadDispatchLinuxBootstrapScript("avalonia-linux-x64-installer", CancellationToken.None);

        var file = Assert.IsType<FileContentResult>(result);
        Assert.Equal("chummer-setup.sh", file.FileDownloadName);
        string script = Encoding.UTF8.GetString(file.FileContents);
        Assert.Contains("blazor-desktop-linux-x64-installer", script, StringComparison.Ordinal);
        Assert.Contains($"https://chummer.run/downloads/install/avalonia-linux-x64-installer/continue.json?ticket={Uri.EscapeDataString(ticket.Ticket)}", script, StringComparison.Ordinal);
        Assert.Contains("dpkg-deb -x", script, StringComparison.Ordinal);
        Assert.Contains("Confirmed linked installs", script, StringComparison.Ordinal);
        Assert.DoesNotContain("claimCode=", script, StringComparison.Ordinal);
        Assert.Equal("private, no-store", fixture.Controller.ControllerContext.HttpContext.Response.Headers.CacheControl.ToString());
    }

    private sealed class Fixture : IDisposable
    {
        private readonly string _root;

        public Fixture()
        {
            _root = Path.Combine(Path.GetTempPath(), "public-landing-dispatch-tests", Guid.NewGuid().ToString("N"));
            string downloadsRoot = Path.Combine(_root, "downloads");
            string filesRoot = Path.Combine(downloadsRoot, "files");
            Directory.CreateDirectory(filesRoot);
            File.WriteAllBytes(Path.Combine(filesRoot, "chummer-avalonia-osx-arm64-installer.dmg"), "avalonia-mac"u8.ToArray());
            File.WriteAllBytes(Path.Combine(filesRoot, "chummer-blazor-desktop-osx-arm64-installer.dmg"), "blazor-mac"u8.ToArray());
            File.WriteAllBytes(Path.Combine(filesRoot, "chummer-avalonia-osx-x64-installer.dmg"), "avalonia-mac-intel"u8.ToArray());
            File.WriteAllBytes(Path.Combine(filesRoot, "chummer-avalonia-win-x64-installer.exe"), "avalonia-win"u8.ToArray());
            File.WriteAllBytes(Path.Combine(filesRoot, "chummer-blazor-desktop-win-x64-installer.exe"), "blazor-win"u8.ToArray());
            File.WriteAllBytes(Path.Combine(filesRoot, "chummer-avalonia-linux-x64-installer.deb"), "avalonia-linux"u8.ToArray());
            File.WriteAllBytes(Path.Combine(filesRoot, "chummer-blazor-desktop-linux-x64-installer.deb"), "blazor-linux"u8.ToArray());
            File.WriteAllText(
                Path.Combine(downloadsRoot, "releases.json"),
                """
                {
                  "version": "run-test",
                  "channel": "preview",
                  "publishedAt": "2026-04-02T20:56:19Z",
                  "proofStatus": "passed",
                  "proofRoutes": [
                    "/downloads/install/avalonia-osx-arm64-installer",
                    "/downloads/file/avalonia-osx-arm64-installer",
                    "/downloads/install/blazor-desktop-osx-arm64-installer",
                    "/downloads/file/blazor-desktop-osx-arm64-installer",
                    "/downloads/install/avalonia-osx-x64-installer",
                    "/downloads/file/avalonia-osx-x64-installer"
                  ],
                  "downloads": [
                    {
                      "id": "avalonia-osx-arm64-installer",
                      "platform": "Avalonia Desktop macOS ARM64 Installer",
                      "url": "/downloads/files/chummer-avalonia-osx-arm64-installer.dmg",
                      "sha256": "a1",
                      "sizeBytes": 101,
                      "head": "avalonia",
                      "platformId": "osx-arm64",
                      "arch": "arm64",
                      "kind": "dmg",
                      "fileName": "chummer-avalonia-osx-arm64-installer.dmg",
                      "installAccessClass": "account_required"
                    },
                    {
                      "id": "blazor-desktop-osx-arm64-installer",
                      "platform": "Blazor Desktop macOS ARM64 Installer",
                      "url": "/downloads/files/chummer-blazor-desktop-osx-arm64-installer.dmg",
                      "sha256": "b2",
                      "sizeBytes": 202,
                      "head": "blazor-desktop",
                      "platformId": "osx-arm64",
                      "arch": "arm64",
                      "kind": "dmg",
                      "fileName": "chummer-blazor-desktop-osx-arm64-installer.dmg",
                      "installAccessClass": "account_required"
                    },
                    {
                      "id": "avalonia-osx-x64-installer",
                      "platform": "Avalonia Desktop macOS X64 Installer",
                      "url": "/downloads/files/chummer-avalonia-osx-x64-installer.dmg",
                      "sha256": "c3",
                      "sizeBytes": 303,
                      "head": "avalonia",
                      "platformId": "osx-x64",
                      "arch": "x64",
                      "kind": "dmg",
                      "fileName": "chummer-avalonia-osx-x64-installer.dmg",
                      "installAccessClass": "account_required"
                    },
                    {
                      "id": "avalonia-win-x64-installer",
                      "platform": "Avalonia Desktop Windows x64 Installer",
                      "url": "/downloads/files/chummer-avalonia-win-x64-installer.exe",
                      "sha256": "d4",
                      "sizeBytes": 404,
                      "head": "avalonia",
                      "platformId": "win-x64",
                      "arch": "x64",
                      "kind": "installer",
                      "fileName": "chummer-avalonia-win-x64-installer.exe",
                      "installAccessClass": "account_required"
                    },
                    {
                      "id": "blazor-desktop-win-x64-installer",
                      "platform": "Blazor Desktop Windows x64 Installer",
                      "url": "/downloads/files/chummer-blazor-desktop-win-x64-installer.exe",
                      "sha256": "e5",
                      "sizeBytes": 505,
                      "head": "blazor-desktop",
                      "platformId": "win-x64",
                      "arch": "x64",
                      "kind": "installer",
                      "fileName": "chummer-blazor-desktop-win-x64-installer.exe",
                      "installAccessClass": "account_required"
                    },
                    {
                      "id": "avalonia-linux-x64-installer",
                      "platform": "Avalonia Desktop Linux x64 Installer",
                      "url": "/downloads/files/chummer-avalonia-linux-x64-installer.deb",
                      "sha256": "f6",
                      "sizeBytes": 606,
                      "head": "avalonia",
                      "platformId": "linux",
                      "arch": "x64",
                      "kind": "installer",
                      "fileName": "chummer-avalonia-linux-x64-installer.deb",
                      "installAccessClass": "account_required"
                    },
                    {
                      "id": "blazor-desktop-linux-x64-installer",
                      "platform": "Blazor Desktop Linux x64 Installer",
                      "url": "/downloads/files/chummer-blazor-desktop-linux-x64-installer.deb",
                      "sha256": "g7",
                      "sizeBytes": 707,
                      "head": "blazor-desktop",
                      "platformId": "linux",
                      "arch": "x64",
                      "kind": "installer",
                      "fileName": "chummer-blazor-desktop-linux-x64-installer.deb",
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
                  "publishedAt": "2026-04-02T20:56:19Z",
                  "status": "published",
                  "artifacts": [
                    {
                      "artifactId": "avalonia-osx-arm64-installer",
                      "head": "avalonia",
                      "platform": "macos",
                      "arch": "arm64",
                      "kind": "dmg",
                      "platformLabel": "Avalonia Desktop macOS ARM64 Installer",
                      "fileName": "chummer-avalonia-osx-arm64-installer.dmg",
                      "downloadUrl": "/downloads/files/chummer-avalonia-osx-arm64-installer.dmg",
                      "sha256": "a1",
                      "sizeBytes": 101,
                      "installAccessClass": "account_required"
                    },
                    {
                      "artifactId": "blazor-desktop-osx-arm64-installer",
                      "head": "blazor-desktop",
                      "platform": "macos",
                      "arch": "arm64",
                      "kind": "dmg",
                      "platformLabel": "Blazor Desktop macOS ARM64 Installer",
                      "fileName": "chummer-blazor-desktop-osx-arm64-installer.dmg",
                      "downloadUrl": "/downloads/files/chummer-blazor-desktop-osx-arm64-installer.dmg",
                      "sha256": "b2",
                      "sizeBytes": 202,
                      "installAccessClass": "account_required"
                    },
                    {
                      "artifactId": "avalonia-osx-x64-installer",
                      "head": "avalonia",
                      "platform": "macos",
                      "arch": "x64",
                      "kind": "dmg",
                      "platformLabel": "Avalonia Desktop macOS X64 Installer",
                      "fileName": "chummer-avalonia-osx-x64-installer.dmg",
                      "downloadUrl": "/downloads/files/chummer-avalonia-osx-x64-installer.dmg",
                      "sha256": "c3",
                      "sizeBytes": 303,
                      "installAccessClass": "account_required"
                    },
                    {
                      "artifactId": "avalonia-win-x64-installer",
                      "head": "avalonia",
                      "platform": "windows",
                      "arch": "x64",
                      "kind": "installer",
                      "platformLabel": "Avalonia Desktop Windows x64 Installer",
                      "fileName": "chummer-avalonia-win-x64-installer.exe",
                      "downloadUrl": "/downloads/files/chummer-avalonia-win-x64-installer.exe",
                      "sha256": "d4",
                      "sizeBytes": 404,
                      "installAccessClass": "account_required"
                    },
                    {
                      "artifactId": "blazor-desktop-win-x64-installer",
                      "head": "blazor-desktop",
                      "platform": "windows",
                      "arch": "x64",
                      "kind": "installer",
                      "platformLabel": "Blazor Desktop Windows x64 Installer",
                      "fileName": "chummer-blazor-desktop-win-x64-installer.exe",
                      "downloadUrl": "/downloads/files/chummer-blazor-desktop-win-x64-installer.exe",
                      "sha256": "e5",
                      "sizeBytes": 505,
                      "installAccessClass": "account_required"
                    },
                    {
                      "artifactId": "avalonia-linux-x64-installer",
                      "head": "avalonia",
                      "platform": "linux",
                      "arch": "x64",
                      "kind": "installer",
                      "platformLabel": "Avalonia Desktop Linux x64 Installer",
                      "fileName": "chummer-avalonia-linux-x64-installer.deb",
                      "downloadUrl": "/downloads/files/chummer-avalonia-linux-x64-installer.deb",
                      "sha256": "f6",
                      "sizeBytes": 606,
                      "installAccessClass": "account_required"
                    },
                    {
                      "artifactId": "blazor-desktop-linux-x64-installer",
                      "head": "blazor-desktop",
                      "platform": "linux",
                      "arch": "x64",
                      "kind": "installer",
                      "platformLabel": "Blazor Desktop Linux x64 Installer",
                      "fileName": "chummer-blazor-desktop-linux-x64-installer.deb",
                      "downloadUrl": "/downloads/files/chummer-blazor-desktop-linux-x64-installer.deb",
                      "sha256": "g7",
                      "sizeBytes": 707,
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
                    ["CHUMMER_INSTALL_BOOTSTRAP_TICKET_LIFETIME_MINUTES"] = "20",
                    ["CHUMMER_INSTALL_CLAIM_TICKET_LIFETIME_HOURS"] = "24",
                    ["CHUMMER_PERSONALIZED_INSTALL_SCRIPT_LIFETIME_HOURS"] = "24"
                })
                .Build();

            ManifestService = new PublicReleaseManifestService(Configuration);
            ReleaseSelection = new ReleaseSelectionService(new PublicCanonFileLoader(Configuration));
            var installLinkingStore = new InstallLinkingStore(Configuration, NullLogger<InstallLinkingStore>.Instance);
            InstallLinking = new InstallLinkingService(installLinkingStore, Configuration);
            IDataProtectionProvider dataProtectionProvider = DataProtectionProvider.Create(new DirectoryInfo(Path.Combine(_root, "keys")));
            InstallBootstrapTickets = new InstallBootstrapTicketService(dataProtectionProvider, Configuration);
            PersonalizedInstallScripts = new PersonalizedInstallScriptService(installLinkingStore, Configuration);
            Controller = new PublicLandingController(
                landing: null!,
                releases: ManifestService,
                campaignOsProof: null!,
                releaseSelection: ReleaseSelection,
                actions: null!,
                accounts: null!,
                identity: null!,
                links: null!,
                experience: null!,
                installLinking: InstallLinking,
                campaignSpine: null!,
                workspaceServerPlane: null!,
                publicCreatorDiscovery: null!,
                chrome: null!,
                trustContent: null!,
                privacyBoundaries: null!,
                trustPulse: null!,
                signedInTrustStatus: null!,
                supportCases: null!,
                supportPresentation: null!,
                configuration: Configuration,
                installBootstrapTickets: InstallBootstrapTickets,
                personalizedInstallScripts: PersonalizedInstallScripts,
                releaseUploadTickets: null!,
                windowsProofInstallers: new WindowsProofInstallerService(Configuration),
                webHostEnvironment: null!,
                logger: NullLogger<PublicLandingController>.Instance);
        }

        public IConfiguration Configuration { get; }

        public PublicReleaseManifestService ManifestService { get; }

        public ReleaseSelectionService ReleaseSelection { get; }

        public InstallLinkingService InstallLinking { get; }

        public InstallBootstrapTicketService InstallBootstrapTickets { get; }

        public PersonalizedInstallScriptService PersonalizedInstallScripts { get; }

        public PublicLandingController Controller { get; }

        public void Dispose()
        {
            if (Directory.Exists(_root))
            {
                Directory.Delete(_root, recursive: true);
            }
        }
    }
}
