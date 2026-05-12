using System.Text;
using Chummer.Run.Api.Controllers;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.Services.InstallLinking;
using Chummer.Run.Api.Services.KarmaForge;
using Chummer.Run.Contracts.PublicSurface;
using Chummer.Run.Contracts.Identity;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.Routing;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using System.Net;
using System.Net.Http;
using System.Security.Cryptography;
using System.Text.Json;
using Xunit;

namespace Chummer.Tests;

public sealed class PublicLandingDownloadDispatchTests
{
    private static string ComputeSha256Hex(string value)
        => Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(value))).ToLowerInvariant();

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
        Assert.Contains("CLAIM_CODES", script, StringComparison.Ordinal);
        Assert.Contains("build_claim_download_url()", script, StringComparison.Ordinal);
        Assert.Contains("HEAD_IDS", script, StringComparison.Ordinal);
        Assert.Contains("wait_for_claim_success", script, StringComparison.Ordinal);
        Assert.Contains("Confirmed linked installs", script, StringComparison.Ordinal);
        Assert.Contains("claimCode=", script, StringComparison.Ordinal);
        Assert.Equal("private, no-store", fixture.Controller.ControllerContext.HttpContext.Response.Headers.CacheControl.ToString());
    }

    [Fact]
    public async Task BootstrapScriptPrefersCanonicalShelfWhenRuntimeRegistryViewDropsMatchingMacArtifact()
    {
        using Fixture fixture = new(
            runtimeManifestJson:
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
                }
              ]
            }
            """);
        var manifest = fixture.ManifestService.LoadManifest();
        var artifact = Assert.Single(manifest.Downloads, item => string.Equals(item.Id, "avalonia-osx-arm64-installer", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(manifest.Downloads, item => string.Equals(item.Id, "blazor-desktop-osx-arm64-installer", StringComparison.OrdinalIgnoreCase));
        IReadOnlyList<PublicReleaseArtifactDto> guidedArtifacts = PublicLandingController.ResolveGuidedBootstrapArtifacts(manifest, artifact);
        Assert.Contains(guidedArtifacts, item => string.Equals(item.Id, "blazor-desktop-osx-arm64-installer", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(guidedArtifacts, item => string.Equals(item.Id, "avalonia-osx-x64-installer", StringComparison.OrdinalIgnoreCase));
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
    }

    [Fact]
    public async Task PersonalizedMacBootstrapScriptCanBeFetchedRepeatedlyAndEmbedsClaimCodes()
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

        IActionResult first = fixture.Controller.DownloadDispatchPersonalizedMacBootstrapScript(issue.ScriptId, issue.Link.RenderedScriptSha256);

        var file = Assert.IsType<FileContentResult>(first);
        string script = Encoding.UTF8.GetString(file.FileContents);
        Assert.Contains("CLAIM_CODES", script, StringComparison.Ordinal);
        Assert.Contains("build_claim_download_url()", script, StringComparison.Ordinal);
        Assert.Contains("https://chummer.run/downloads/file/avalonia-osx-arm64-installer", script, StringComparison.Ordinal);
        Assert.Contains("claimCode=", script, StringComparison.Ordinal);
        Assert.Equal("private, no-store", fixture.Controller.ControllerContext.HttpContext.Response.Headers.CacheControl.ToString());

        IActionResult second = fixture.Controller.DownloadDispatchPersonalizedMacBootstrapScript(issue.ScriptId, issue.Link.RenderedScriptSha256);

        var secondFile = Assert.IsType<FileContentResult>(second);
        Assert.Contains("CLAIM_CODES", Encoding.UTF8.GetString(secondFile.FileContents), StringComparison.Ordinal);
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

        IActionResult result = fixture.Controller.DownloadDispatchPersonalizedMacBootstrapScript(issue.ScriptId, issue.Link.RenderedScriptSha256);

        var file = Assert.IsType<FileContentResult>(result);
        Assert.Equal(renderedScript, Encoding.UTF8.GetString(file.FileContents));
    }

    [Fact]
    public void PersonalizedMacBootstrapScriptDigestMatchesStoredScriptBytes()
    {
        using Fixture fixture = new();
        const string renderedScript = "#!/usr/bin/env bash\nprintf 'ok\\n'\n";
        string expectedDigest = ComputeSha256Hex(renderedScript);
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

        IActionResult result = fixture.Controller.DownloadDispatchPersonalizedMacBootstrapScript(issue.ScriptId, issue.Link.RenderedScriptSha256);

        var file = Assert.IsType<FileContentResult>(result);
        string servedScript = Encoding.UTF8.GetString(file.FileContents);
        Assert.Equal(renderedScript, servedScript);
        Assert.Equal(expectedDigest, issue.Link.RenderedScriptSha256);
        Assert.Equal(expectedDigest, ComputeSha256Hex(servedScript));
    }

    [Fact]
    public void PersonalizedMacBootstrapScriptRepairsLegacyTrimmedScriptWhenDigestPinnedTrailingNewline()
    {
        using Fixture fixture = new();
        const string renderedScript = "#!/usr/bin/env bash\nprintf 'ok\\n'\n";
        string legacyTrimmedScript = renderedScript.TrimEnd('\n');
        string expectedDigest = ComputeSha256Hex(renderedScript);
        var issue = fixture.PersonalizedInstallScripts.IssueMacScript(
            "avalonia-osx-arm64-installer",
            ["avalonia-osx-arm64-installer"],
            "user-archon",
            "subject-archon",
            legacyTrimmedScript);

        lock (fixture.InstallLinkingStore.Gate)
        {
            fixture.InstallLinkingStore.PersonalizedInstallScriptsById[issue.ScriptId] = issue.Link with
            {
                RenderedScript = legacyTrimmedScript,
                RenderedScriptSha256 = expectedDigest
            };
            fixture.InstallLinkingStore.PersistLocked();
        }

        fixture.Controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };
        fixture.Controller.ControllerContext.HttpContext.Request.Scheme = "https";
        fixture.Controller.ControllerContext.HttpContext.Request.Host = new HostString("chummer.run");

        IActionResult result = fixture.Controller.DownloadDispatchPersonalizedMacBootstrapScript(issue.ScriptId, expectedDigest);

        var file = Assert.IsType<FileContentResult>(result);
        string servedScript = Encoding.UTF8.GetString(file.FileContents);
        Assert.Equal(renderedScript, servedScript);
        Assert.Equal(expectedDigest, ComputeSha256Hex(servedScript));
    }

    [Fact]
    public void PersonalizedMacBootstrapScriptRejectsMismatchedDigestPath()
    {
        using Fixture fixture = new();
        var issue = fixture.PersonalizedInstallScripts.IssueMacScript(
            "avalonia-osx-arm64-installer",
            ["avalonia-osx-arm64-installer"],
            "user-archon",
            "subject-archon",
            "#!/usr/bin/env bash\nprintf 'ok\\n'");

        fixture.Controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };

        IActionResult result = fixture.Controller.DownloadDispatchPersonalizedMacBootstrapScript(issue.ScriptId, "deadbeef");

        Assert.IsType<NotFoundResult>(result);
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

    [Fact]
    public async Task SignedInWindowsContinuationRouteIssuesRecoveryClaimWithoutBootstrapTicket()
    {
        using Fixture fixture = new(authenticated: true);
        fixture.Controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };
        fixture.Controller.ControllerContext.HttpContext.Request.Scheme = "https";
        fixture.Controller.ControllerContext.HttpContext.Request.Host = new HostString("chummer.run");
        fixture.Controller.ControllerContext.HttpContext.Request.Headers.Authorization = "Bearer desktop-access-token";

        IActionResult result = await fixture.Controller.DownloadDispatchBootstrapClaim("avalonia-win-x64-installer", CancellationToken.None);

        var ok = Assert.IsType<OkObjectResult>(result);
        using JsonDocument payload = JsonSerializer.SerializeToDocument(ok.Value);
        Assert.Equal("avalonia-win-x64-installer", payload.RootElement.GetProperty("artifactId").GetString());
        Assert.False(payload.RootElement.GetProperty("recoveryModeOnly").GetBoolean());
        Assert.False(string.IsNullOrWhiteSpace(payload.RootElement.GetProperty("claimCode").GetString()));
        Assert.Equal("/account/access", payload.RootElement.GetProperty("accountHref").GetString());
        Assert.Equal("private, no-store", fixture.Controller.ControllerContext.HttpContext.Response.Headers.CacheControl.ToString());
    }

    private sealed class Fixture : IDisposable
    {
        private readonly string _root;

        public Fixture(bool authenticated = false, string? runtimeManifestJson = null)
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

            Dictionary<string, string?> settings = new()
            {
                ["CHUMMER_DOWNLOADS_SOURCE_ROOT"] = downloadsRoot,
                ["CHUMMER_PUBLIC_CANON_ROOT"] = RepoPaths.Root,
                ["CHUMMER_INSTALL_LINKING_STORE_PATH"] = Path.Combine(_root, "install-linking.json"),
                ["CHUMMER_INSTALL_BOOTSTRAP_TICKET_LIFETIME_MINUTES"] = "20",
                ["CHUMMER_INSTALL_CLAIM_TICKET_LIFETIME_HOURS"] = "24",
                ["CHUMMER_PERSONALIZED_INSTALL_SCRIPT_LIFETIME_HOURS"] = "24",
                ["CHUMMER_COMMUNITY_STORE_PATH"] = Path.Combine(_root, "community-store.json"),
                ["IDENTITY_SERVICE_BASE_URL"] = "http://identity.example"
            };
            if (!string.IsNullOrWhiteSpace(runtimeManifestJson))
            {
                settings["CHUMMER_RELEASE_REGISTRY_CURRENT_URL"] = "https://registry.local/api/v1/registry/release-channel/current";
            }

            Configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(settings)
                .Build();

            HttpClient? runtimeManifestClient = string.IsNullOrWhiteSpace(runtimeManifestJson)
                ? null
                : new HttpClient(new StaticJsonHandler(runtimeManifestJson));
            ManifestService = new PublicReleaseManifestService(Configuration, runtimeManifestClient);
            ReleaseSelection = new ReleaseSelectionService(new PublicCanonFileLoader(Configuration));
            HubIdentityClient identity = new(
                new HttpClient(new IdentityHandler(authenticated))
                {
                    BaseAddress = new Uri("http://identity.example")
                },
                Configuration,
                NullLogger<HubIdentityClient>.Instance);
            CommunityStore communityStore = new(Configuration, NullLogger<CommunityStore>.Instance);
            Accounts = new AccountService(communityStore);
            ParticipationOperatorNotificationService participationNotifications = new(
                new HttpClient(new StaticJsonHandler("""{"target_ref":"delivery-test"}""")),
                communityStore,
                Configuration,
                NullLogger<ParticipationOperatorNotificationService>.Instance);
            InstallLinkingStore = new InstallLinkingStore(Configuration, NullLogger<InstallLinkingStore>.Instance);
            InstallLinking = new InstallLinkingService(InstallLinkingStore, Configuration);
            IDataProtectionProvider dataProtectionProvider = DataProtectionProvider.Create(new DirectoryInfo(Path.Combine(_root, "keys")));
            InstallBootstrapTickets = new InstallBootstrapTicketService(dataProtectionProvider, Configuration);
            PersonalizedInstallScripts = new PersonalizedInstallScriptService(InstallLinkingStore, Configuration);
            Controller = new PublicLandingController(
                landing: null!,
                flagshipCoverage: null!,
                releases: ManifestService,
                campaignOsProof: null!,
                releaseSelection: ReleaseSelection,
                actions: null!,
                accounts: Accounts,
                identity: identity,
                links: null!,
                experience: null!,
                participationNotifications: participationNotifications,
                installLinking: InstallLinking,
                campaignSpine: null!,
                workspaceServerPlane: null!,
                karmaForge: new KarmaForgeDiscoveryService(new KarmaForgeStore(Configuration, NullLogger<KarmaForgeStore>.Instance), Configuration),
                packageCatalog: new PublicPackageCatalogService(),
                publicCreatorDiscovery: null!,
                chrome: null!,
                trustContent: null!,
                privacyBoundaries: null!,
                signalProjection: null!,
                signalOperations: null!,
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

        public AccountService Accounts { get; }

        public PublicReleaseManifestService ManifestService { get; }

        public ReleaseSelectionService ReleaseSelection { get; }

        public InstallLinkingService InstallLinking { get; }

        public InstallLinkingStore InstallLinkingStore { get; }

        public InstallBootstrapTicketService InstallBootstrapTickets { get; }

        public PersonalizedInstallScriptService PersonalizedInstallScripts { get; }

        public PublicLandingController Controller { get; }

        private sealed class IdentityHandler : HttpMessageHandler
        {
            private readonly bool _authenticated;

            public IdentityHandler(bool authenticated)
            {
                _authenticated = authenticated;
            }

            protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
            {
                if (!_authenticated)
                {
                    return Task.FromResult(new HttpResponseMessage(HttpStatusCode.Unauthorized)
                    {
                        Content = new StringContent(string.Empty, Encoding.UTF8, "application/json")
                    });
                }

                if (request.RequestUri?.AbsolutePath.EndsWith("/api/v1/identity/introspect", StringComparison.Ordinal) == true)
                {
                    return Task.FromResult(JsonResponse(new IdentityIntrospectionResponse(
                        Active: true,
                        SessionId: "session.dispatch",
                        SubjectId: "subject.dispatch",
                        Roles: ["user"],
                        ExpiresAtUtc: DateTimeOffset.Parse("2026-04-03T20:00:00Z"))));
                }

                if (request.RequestUri?.AbsolutePath.EndsWith("/api/v1/identity/subjects/subject.dispatch", StringComparison.Ordinal) == true)
                {
                    return Task.FromResult(JsonResponse(new IdentitySubjectResponse(
                        SubjectId: "subject.dispatch",
                        DisplayName: "Dispatch User",
                        Email: "dispatch@example.com",
                        Roles: ["user"],
                        UpdatedAtUtc: DateTimeOffset.Parse("2026-04-02T20:00:00Z"))));
                }

                throw new InvalidOperationException($"unexpected identity request: {request.RequestUri}");
            }

            private static HttpResponseMessage JsonResponse<T>(T payload)
                => new(HttpStatusCode.OK)
                {
                    Content = new StringContent(JsonSerializer.Serialize(payload), Encoding.UTF8, "application/json")
                };
        }

        private sealed class StaticJsonHandler : HttpMessageHandler
        {
            private readonly string _payload;

            public StaticJsonHandler(string payload)
            {
                _payload = payload;
            }

            protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
                => Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK)
                {
                    Content = new StringContent(_payload, Encoding.UTF8, "application/json")
                });
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
