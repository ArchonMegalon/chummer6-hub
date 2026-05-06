using Chummer.Run.Api.Controllers;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.Services.InstallLinking;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.Routing;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using System.Text.Json;
using Xunit;

namespace Chummer.Tests;

public sealed class DownloadsCompatibilityControllerTests
{
    [Fact]
    public void WindowsProofInstallerRoutes_Advertise_Head_And_Get_For_Probe_Safe_Binary_Downloads()
    {
        var byFile = typeof(DownloadsCompatibilityController).GetMethod(nameof(DownloadsCompatibilityController.DownloadWindowsProofInstaller));
        Assert.NotNull(byFile);

        var byArtifact = typeof(DownloadsCompatibilityController).GetMethod(nameof(DownloadsCompatibilityController.DownloadWindowsProofInstallerByArtifactId));
        Assert.NotNull(byArtifact);

        var byFileRoutes = byFile!
            .GetCustomAttributes(typeof(HttpMethodAttribute), inherit: true)
            .Cast<HttpMethodAttribute>()
            .ToArray();
        var byArtifactRoutes = byArtifact!
            .GetCustomAttributes(typeof(HttpMethodAttribute), inherit: true)
            .Cast<HttpMethodAttribute>()
            .ToArray();

        Assert.Contains(byFileRoutes, route =>
            string.Equals(route.Template, "/downloads/proof/windows/{fileName}", StringComparison.Ordinal)
            && route.HttpMethods.Contains("GET", StringComparer.OrdinalIgnoreCase));
        Assert.Contains(byFileRoutes, route =>
            string.Equals(route.Template, "/downloads/proof/windows/{fileName}", StringComparison.Ordinal)
            && route.HttpMethods.Contains("HEAD", StringComparer.OrdinalIgnoreCase));
        Assert.Contains(byArtifactRoutes, route =>
            string.Equals(route.Template, "/downloads/install/{artifactId}/proof", StringComparison.Ordinal)
            && route.HttpMethods.Contains("GET", StringComparer.OrdinalIgnoreCase));
        Assert.Contains(byArtifactRoutes, route =>
            string.Equals(route.Template, "/downloads/install/{artifactId}/proof", StringComparison.Ordinal)
            && route.HttpMethods.Contains("HEAD", StringComparer.OrdinalIgnoreCase));
    }

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
    public void CanonicalReleaseManifestFiltersDisabledArtifactsWhenSuppressionIsConfigured()
    {
        using Fixture fixture = new(new Dictionary<string, string?>
        {
            ["CHUMMER_PUBLIC_DISABLED_ARTIFACT_IDS"] = "avalonia-win-x64-installer"
        });

        IActionResult result = fixture.Controller.CanonicalReleaseManifest();

        var content = Assert.IsType<ContentResult>(result);
        using JsonDocument document = JsonDocument.Parse(content.Content ?? "{}");
        JsonElement artifacts = document.RootElement.GetProperty("artifacts");
        Assert.DoesNotContain(artifacts.EnumerateArray(), artifact =>
            string.Equals(artifact.GetProperty("artifactId").GetString(), "avalonia-win-x64-installer", StringComparison.OrdinalIgnoreCase));
        JsonElement coverage = document.RootElement.GetProperty("desktopTupleCoverage");
        Assert.Contains("windows", coverage.GetProperty("missingRequiredPlatforms").EnumerateArray().Select(static value => value.GetString()));
    }

    [Fact]
    public void ReleaseManifestKeepsGeneratedTimestampAliases()
    {
        using Fixture fixture = new();

        IActionResult result = fixture.Controller.ReleaseManifest();

        OkObjectResult ok = Assert.IsType<OkObjectResult>(result);
        string payload = JsonSerializer.Serialize(ok.Value, new JsonSerializerOptions(JsonSerializerDefaults.Web));
        using JsonDocument document = JsonDocument.Parse(payload);
        Assert.Equal("Chummer.Hub.Registry.Contracts", document.RootElement.GetProperty("contractName").GetString());
        Assert.Equal("Chummer.Hub.Registry.Contracts", document.RootElement.GetProperty("contract_name").GetString());
        Assert.Equal("2026-04-02T16:15:00+00:00", document.RootElement.GetProperty("generatedAt").GetString());
        Assert.Equal("2026-04-02T16:15:00+00:00", document.RootElement.GetProperty("generated_at").GetString());
    }

    [Fact]
    public void ReleaseManifestPreservesCanonicalRidBackedPlatformIdsAndTupleCoverage()
    {
        using Fixture fixture = new();

        IActionResult result = fixture.Controller.ReleaseManifest();

        OkObjectResult ok = Assert.IsType<OkObjectResult>(result);
        string payload = JsonSerializer.Serialize(ok.Value, new JsonSerializerOptions(JsonSerializerDefaults.Web));
        using JsonDocument document = JsonDocument.Parse(payload);
        JsonElement downloads = document.RootElement.GetProperty("downloads");
        Assert.Contains(downloads.EnumerateArray(), item =>
            string.Equals(item.GetProperty("id").GetString(), "avalonia-win-x64-installer", StringComparison.OrdinalIgnoreCase)
            && string.Equals(item.GetProperty("platformId").GetString(), "win-x64", StringComparison.OrdinalIgnoreCase));

        JsonElement coverage = document.RootElement.GetProperty("desktopTupleCoverage");
        Assert.Contains(coverage.GetProperty("promotedInstallerTuples").EnumerateArray(), item =>
            string.Equals(item.GetProperty("tupleId").GetString(), "avalonia:windows:win-x64", StringComparison.OrdinalIgnoreCase)
            && string.Equals(item.GetProperty("rid").GetString(), "win-x64", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(coverage.GetProperty("missingRequiredPlatformHeadRidTuples").EnumerateArray(), item =>
            string.Equals(item.GetString(), "avalonia:osx-arm64:macos", StringComparison.OrdinalIgnoreCase));
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
        Assert.StartsWith("/auth/google/start?next=", redirect.Url, StringComparison.Ordinal);
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
        Assert.StartsWith("/auth/google/start?next=", redirect.Url, StringComparison.Ordinal);
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

    [Fact]
    public void WindowsProofInstallersCatalogListsStagedFiles()
    {
        using Fixture fixture = new();

        IActionResult result = fixture.Controller.WindowsProofInstallers();

        var ok = Assert.IsType<OkObjectResult>(result);
        string payload = JsonSerializer.Serialize(ok.Value);
        Assert.Contains("\"status\":\"proof_only\"", payload, StringComparison.Ordinal);
        Assert.Contains("verification and support rail", payload, StringComparison.Ordinal);
        Assert.Contains("chummer-avalonia-win-x64-installer.exe", payload, StringComparison.Ordinal);
        Assert.Contains("chummer-blazor-desktop-win-x64-installer.exe", payload, StringComparison.Ordinal);
    }

    [Fact]
    public void WindowsProofInstallersCatalogUsesSupplementalMissingMessageWhenEmpty()
    {
        using Fixture fixture = new();
        Directory.Delete(fixture.ProofRoot, recursive: true);
        Directory.CreateDirectory(fixture.ProofRoot);

        IActionResult result = fixture.Controller.WindowsProofInstallers();

        var notFound = Assert.IsType<NotFoundObjectResult>(result);
        string payload = JsonSerializer.Serialize(notFound.Value);
        Assert.Contains("\"status\":\"missing\"", payload, StringComparison.Ordinal);
        Assert.Contains("No staged Windows supplemental installers are available right now.", payload, StringComparison.Ordinal);
        Assert.DoesNotContain("preview installers", payload, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void WindowsProofInstallerDownloadServesStagedFile()
    {
        using Fixture fixture = new();
        fixture.Controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };

        IActionResult result = fixture.Controller.DownloadWindowsProofInstaller("chummer-avalonia-win-x64-installer.exe");

        var file = Assert.IsType<PhysicalFileResult>(result);
        Assert.EndsWith("proof/windows/chummer-avalonia-win-x64-installer.exe", file.FileName, StringComparison.Ordinal);
        Assert.Equal("chummer-avalonia-win-x64-installer.exe", file.FileDownloadName);
        Assert.Equal("private, no-store, max-age=0", fixture.Controller.ControllerContext.HttpContext.Response.Headers.CacheControl.ToString());
        Assert.Equal("no-cache", fixture.Controller.ControllerContext.HttpContext.Response.Headers.Pragma.ToString());
        Assert.Equal("0", fixture.Controller.ControllerContext.HttpContext.Response.Headers.Expires.ToString());
        Assert.Equal("proof-only", fixture.Controller.ControllerContext.HttpContext.Response.Headers["X-Chummer-Install-Tier"].ToString());
    }

    [Fact]
    public void WindowsProofInstallerArtifactRouteServesStagedFile()
    {
        using Fixture fixture = new();
        fixture.Controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };

        IActionResult result = fixture.Controller.DownloadWindowsProofInstallerByArtifactId("avalonia-win-x64-installer");

        var file = Assert.IsType<PhysicalFileResult>(result);
        Assert.EndsWith("proof/windows/chummer-avalonia-win-x64-installer.exe", file.FileName, StringComparison.Ordinal);
        Assert.Equal("chummer-avalonia-win-x64-installer.exe", file.FileDownloadName);
        Assert.Equal("private, no-store, max-age=0", fixture.Controller.ControllerContext.HttpContext.Response.Headers.CacheControl.ToString());
        Assert.Equal("no-cache", fixture.Controller.ControllerContext.HttpContext.Response.Headers.Pragma.ToString());
        Assert.Equal("0", fixture.Controller.ControllerContext.HttpContext.Response.Headers.Expires.ToString());
        Assert.Equal("proof-only", fixture.Controller.ControllerContext.HttpContext.Response.Headers["X-Chummer-Install-Tier"].ToString());
    }

    [Fact]
    public void WindowsProofInstallerDownloadRejectsUnknownFiles()
    {
        using Fixture fixture = new();

        IActionResult result = fixture.Controller.DownloadWindowsProofInstaller("../outside.exe");

        Assert.IsType<NotFoundResult>(result);
    }

    [Fact]
    public void WindowsProofInstallerArtifactRouteRejectsUnknownArtifact()
    {
        using Fixture fixture = new();

        IActionResult result = fixture.Controller.DownloadWindowsProofInstallerByArtifactId("avalonia-win-arm64-installer");

        Assert.IsType<NotFoundResult>(result);
    }

    [Fact]
    public void WindowsProofInstallerRoutesRejectPayloadlessInstaller()
    {
        using Fixture fixture = new();
        File.WriteAllBytes(
            Path.Combine(fixture.ProofRoot, "chummer-avalonia-win-x64-installer.exe"),
            "payload-missing"u8.ToArray());

        IActionResult fileResult = fixture.Controller.DownloadWindowsProofInstaller("chummer-avalonia-win-x64-installer.exe");
        IActionResult artifactResult = fixture.Controller.DownloadWindowsProofInstallerByArtifactId("avalonia-win-x64-installer");
        IActionResult catalogResult = fixture.Controller.WindowsProofInstallers();

        Assert.IsType<NotFoundResult>(fileResult);
        Assert.IsType<NotFoundResult>(artifactResult);

        var ok = Assert.IsType<OkObjectResult>(catalogResult);
        string payload = JsonSerializer.Serialize(ok.Value);
        Assert.DoesNotContain("chummer-avalonia-win-x64-installer.exe", payload, StringComparison.Ordinal);
        Assert.Contains("chummer-blazor-desktop-win-x64-installer.exe", payload, StringComparison.Ordinal);
    }

    [Fact]
    public void WindowsProofInstallersCatalogFallsBackToPublishedInstallerShelf()
    {
        using Fixture fixture = new();
        string downloadsRoot = fixture.Configuration["CHUMMER_DOWNLOADS_SOURCE_ROOT"]!;
        string proofPath = Path.Combine(fixture.ProofRoot, "chummer-avalonia-win-x64-installer.exe");
        string publishedInstallerPath = Path.Combine(downloadsRoot, "files", "chummer-avalonia-win-x64-installer.exe");

        File.Delete(proofPath);
        WriteEmbeddedPayloadInstaller(publishedInstallerPath, "avalonia");

        IActionResult result = fixture.Controller.WindowsProofInstallers();

        var ok = Assert.IsType<OkObjectResult>(result);
        string payload = JsonSerializer.Serialize(ok.Value);
        Assert.Contains("\"status\":\"proof_only\"", payload, StringComparison.Ordinal);
        Assert.Contains("chummer-avalonia-win-x64-installer.exe", payload, StringComparison.Ordinal);
    }

    [Fact]
    public void WindowsProofInstallersCatalogCanOmitInstallersAlreadyPublishedOnTheMainShelf()
    {
        using Fixture fixture = new();
        var service = new WindowsProofInstallerService(fixture.Configuration);

        var catalog = service.LoadCatalog(["avalonia-win-x64-installer"]);

        Assert.DoesNotContain(catalog, item => string.Equals(item.ArtifactId, "avalonia-win-x64-installer", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(catalog, item => string.Equals(item.ArtifactId, "blazor-desktop-win-x64-installer", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void DisabledWindowsArtifactsDoNotSurfaceThroughProofRoutes()
    {
        using Fixture fixture = new(new Dictionary<string, string?>
        {
            ["CHUMMER_PUBLIC_DISABLED_ARTIFACT_IDS"] = "avalonia-win-x64-installer blazor-desktop-win-x64-installer"
        });

        IActionResult catalog = fixture.Controller.WindowsProofInstallers();
        IActionResult byFile = fixture.Controller.DownloadWindowsProofInstaller("chummer-avalonia-win-x64-installer.exe");
        IActionResult byArtifact = fixture.Controller.DownloadWindowsProofInstallerByArtifactId("avalonia-win-x64-installer");

        Assert.IsType<NotFoundObjectResult>(catalog);
        Assert.IsType<NotFoundResult>(byFile);
        Assert.IsType<NotFoundResult>(byArtifact);
    }

    private static void WriteEmbeddedPayloadInstaller(string path, string head)
    {
        File.WriteAllBytes(
            path,
            System.Text.Encoding.UTF8.GetBytes(
                $"stub-{head}-binary\0ChummerInstaller.Payload.zip\0Samples/Legacy/Soma-Career.chum5\0tail"));
    }

    private sealed class Fixture : IDisposable
    {
        private readonly string _root;

        public Fixture(IReadOnlyDictionary<string, string?>? additionalSettings = null)
        {
            _root = Path.Combine(Path.GetTempPath(), "downloads-compatibility-controller-tests", Guid.NewGuid().ToString("N"));
            string downloadsRoot = Path.Combine(_root, "downloads");
            string filesRoot = Path.Combine(downloadsRoot, "files");
            string proofRoot = Path.Combine(downloadsRoot, "proof", "windows");
            Directory.CreateDirectory(filesRoot);
            Directory.CreateDirectory(proofRoot);
            File.WriteAllBytes(Path.Combine(filesRoot, "chummer-avalonia-osx-x64-installer.dmg"), "mac-preview"u8.ToArray());
            File.WriteAllBytes(Path.Combine(filesRoot, "chummer-avalonia-win-x64-installer.exe"), "win-preview"u8.ToArray());
            WriteProofInstaller(Path.Combine(proofRoot, "chummer-avalonia-win-x64-installer.exe"), "avalonia");
            WriteProofInstaller(Path.Combine(proofRoot, "chummer-blazor-desktop-win-x64-installer.exe"), "blazor-desktop");
            File.WriteAllText(
                Path.Combine(downloadsRoot, "releases.json"),
                """
                {
                  "version": "run-test",
                  "channel": "preview",
                  "generatedAt": "2026-04-02T16:15:00Z",
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
                  "generatedAt": "2026-04-02T16:15:00Z",
                  "publishedAt": "2026-04-02T16:14:30Z",
                  "status": "published",
                  "desktopTupleCoverage": {
                    "requiredDesktopPlatforms": ["linux", "windows", "macos"],
                    "requiredDesktopHeads": ["avalonia"],
                    "requiredDesktopPlatformHeadRidTuples": ["avalonia:linux-x64:linux", "avalonia:win-x64:windows", "avalonia:osx-arm64:macos"],
                    "missingRequiredPlatforms": ["linux", "macos"],
                    "missingRequiredHeads": [],
                    "missingRequiredPlatformHeadPairs": ["avalonia:linux", "avalonia:macos"],
                    "missingRequiredPlatformHeadRidTuples": ["avalonia:linux-x64:linux", "avalonia:osx-arm64:macos"],
                    "promotedInstallerTuples": [
                      {
                        "tupleId": "avalonia:windows:win-x64",
                        "head": "avalonia",
                        "platform": "windows",
                        "rid": "win-x64",
                        "arch": "x64",
                        "kind": "installer",
                        "artifactId": "avalonia-win-x64-installer"
                      }
                    ],
                    "promotedPlatformHeads": {
                      "linux": [],
                      "windows": ["avalonia"],
                      "macos": []
                    },
                    "promotedPlatformHeadRidTuples": ["avalonia:win-x64:windows"],
                    "externalProofRequests": [],
                    "desktopRouteTruth": [
                      { "artifactId": "avalonia-win-x64-installer" }
                    ],
                    "complete": false
                  },
                  "artifacts": [
                    {
                      "artifactId": "avalonia-osx-x64-installer",
                      "head": "avalonia",
                      "platform": "macos",
                      "rid": "osx-x64",
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
                      "rid": "win-x64",
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
                }.Concat(additionalSettings ?? new Dictionary<string, string?>())
                    .ToDictionary(static entry => entry.Key, static entry => entry.Value))
                .Build();

            ManifestService = new PublicReleaseManifestService(Configuration);
            ReleaseSelection = new ReleaseSelectionService(new PublicCanonFileLoader(Configuration));
            InstallBootstrapTickets = new InstallBootstrapTicketService(
                Microsoft.AspNetCore.DataProtection.DataProtectionProvider.Create(new DirectoryInfo(Path.Combine(_root, "keys"))),
                Configuration);
            InstallLinking = new InstallLinkingService(new InstallLinkingStore(Configuration, NullLogger<InstallLinkingStore>.Instance), Configuration);
            var windowsProofInstallers = new WindowsProofInstallerService(Configuration);
            var identityClient = new HubIdentityClient(new HttpClient(), Configuration, NullLogger<HubIdentityClient>.Instance);
            Controller = new DownloadsCompatibilityController(
                ManifestService,
                windowsProofInstallers,
                ReleaseSelection,
                InstallLinking,
                InstallBootstrapTickets,
                identityClient,
                Configuration,
                NullLogger<DownloadsCompatibilityController>.Instance);
        }

        public IConfiguration Configuration { get; }

        public string ProofRoot => Path.Combine(_root, "downloads", "proof", "windows");

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

        private static void WriteProofInstaller(string path, string head)
        {
            File.WriteAllBytes(
                path,
                System.Text.Encoding.UTF8.GetBytes(
                    $"stub-{head}-binary\0ChummerInstaller.Payload.zip\0Samples/Legacy/Soma-Career.chum5\0tail"));
        }
    }
}
