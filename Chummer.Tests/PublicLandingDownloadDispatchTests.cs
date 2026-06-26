using System.Text;
using Chummer.Run.Api.Controllers;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.Services.InstallLinking;
using Chummer.Run.Api.Services.KarmaForge;
using Chummer.Run.Api.Services.Support;
using Chummer.Run.Api.ViewModels;
using Chummer.Run.Contracts.PublicSurface;
using Chummer.Run.Contracts.Identity;
using Chummer.Run.Registry.Services;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.Routing;
using Microsoft.AspNetCore.WebUtilities;
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

    private static string NormalizeHorizonCapabilityEnvToken(string value)
        => new(value.Select(static c => char.IsLetterOrDigit(c) ? char.ToUpperInvariant(c) : '_').ToArray());

    private static void AssertProtectedMediaRedirect(string? url, string expectedPath)
    {
        Assert.False(string.IsNullOrWhiteSpace(url));
        Uri uri = new(new Uri("https://chummer.run"), url!);
        Assert.Equal(expectedPath, uri.AbsolutePath);
        var query = QueryHelpers.ParseQuery(uri.Query);
        Assert.True(query.TryGetValue("artifactAccess", out var artifactAccess));
        Assert.False(string.IsNullOrWhiteSpace(artifactAccess.ToString()));
    }

    private static void AssertProtectedMediaUrl(string? url, string expectedPath)
    {
        Assert.False(string.IsNullOrWhiteSpace(url));
        Uri uri = new(new Uri("https://chummer.run"), url!);
        Assert.Equal(expectedPath, uri.AbsolutePath);
        var query = QueryHelpers.ParseQuery(uri.Query);
        Assert.True(query.TryGetValue("artifactAccess", out var artifactAccess));
        Assert.False(string.IsNullOrWhiteSpace(artifactAccess.ToString()));
    }

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
    public async Task UnauthenticatedDownloadDispatchPageRedirectsToWebsiteLogin()
    {
        using Fixture fixture = new(authenticated: false);
        fixture.Controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };
        fixture.Controller.ControllerContext.HttpContext.Request.Scheme = "https";
        fixture.Controller.ControllerContext.HttpContext.Request.Host = new HostString("chummer.run");

        IActionResult result = await fixture.Controller.DownloadDispatchPage("avalonia-win-x64-installer", CancellationToken.None);

        var redirect = Assert.IsType<RedirectResult>(result);
        Assert.Equal("/login?next=%2Fdownloads%2Finstall%2Favalonia-win-x64-installer", redirect.Url);
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

    [Fact]
    public async Task PublicNewsreelJsonReturnsTurnZeroToOneContract()
    {
        using Fixture fixture = new();

        IActionResult result = await fixture.Controller.LedgerTurnNewsreelJson("1", CancellationToken.None);

        var ok = Assert.IsType<OkObjectResult>(result);
        using JsonDocument payload = JsonSerializer.SerializeToDocument(ok.Value);
        Assert.Equal(0, payload.RootElement.GetProperty("FromTurn").GetInt32());
        Assert.Equal(1, payload.RootElement.GetProperty("ToTurn").GetInt32());
        Assert.Equal("Turn 0 -> Turn 1", payload.RootElement.GetProperty("TransitionLabel").GetString());
        Assert.Contains("Turn 0", payload.RootElement.GetProperty("TransitionNarrative").GetString(), StringComparison.Ordinal);
        Assert.True(payload.RootElement.GetProperty("NewsreelBullets").GetArrayLength() > 0);
        JsonElement capability = payload.RootElement.GetProperty("ArtifactCapability");
        Assert.Equal("black-ledger", capability.GetProperty("HorizonId").GetString());
        Assert.Equal("black-ledger-newsroom", capability.GetProperty("CapabilityId").GetString());
        Assert.Equal("newsroom_bulletin", capability.GetProperty("ArtifactKind").GetString());
        Assert.Equal("Newsroom Bulletin", capability.GetProperty("PublicLabel").GetString());
        Assert.Equal("public_bulletin_media", capability.GetProperty("CapabilitySlot").GetString());
        Assert.Equal("available", capability.GetProperty("Status").GetString());
        Assert.Equal("black-ledger:turn-1:newsroom", capability.GetProperty("SourceRef").GetString());
        JsonElement broadcast = payload.RootElement.GetProperty("Broadcast");
        AssertProtectedMediaUrl(broadcast.GetProperty("VideoMp4Href").GetString(), "/media/ledger/newsreels/turn-1-newsreel.mp4");
        AssertProtectedMediaUrl(broadcast.GetProperty("VideoWebmHref").GetString(), "/media/ledger/newsreels/turn-1-newsreel.webm");
        AssertProtectedMediaUrl(broadcast.GetProperty("PosterHref").GetString(), "/media/ledger/newsreels/turn-1-newsreel-poster.png");
        AssertProtectedMediaUrl(broadcast.GetProperty("CaptionsHref").GetString(), "/media/ledger/newsreels/turn-1-newsreel.vtt");
        Assert.DoesNotContain("Emailit", JsonSerializer.Serialize(ok.Value), StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("Signitic", JsonSerializer.Serialize(ok.Value), StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("vidBoard", JsonSerializer.Serialize(ok.Value), StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task BlackLedgerPageIncludesPublicSafeDigestCapabilityMetadata()
    {
        using Fixture fixture = new(configureSettings: settings =>
        {
            settings["CHUMMER_HORIZON_BLACK_LEDGER_CAPABILITY_BLACK_LEDGER_DIGEST_ENABLED"] = "true";
        });
        fixture.Controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };
        fixture.Controller.ControllerContext.HttpContext.Request.Path = "/ledger/map";

        IActionResult result = await fixture.Controller.LedgerMapPage(turn: 1, mode: null, CancellationToken.None);

        ViewResult view = Assert.IsType<ViewResult>(result);
        BlackLedgerHubPageViewModel model = Assert.IsType<BlackLedgerHubPageViewModel>(view.Model);
        Assert.NotNull(model.DigestCapability);
        Assert.Equal("black-ledger", model.DigestCapability!.HorizonId);
        Assert.Equal("black-ledger-digest", model.DigestCapability.CapabilityId);
        Assert.Equal("available", model.DigestCapability.Status);
        Assert.True(model.DigestCapability.RequestSupported);
        Assert.Equal("black-ledger:turn-1:digest", model.DigestCapability.SourceRef);
        Assert.Equal("/ledger/turns/1/digest", model.SecondaryAction.Href);
        Assert.DoesNotContain("Emailit", JsonSerializer.Serialize(model.DigestCapability), StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("Signitic", JsonSerializer.Serialize(model.DigestCapability), StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("vidBoard", JsonSerializer.Serialize(model.DigestCapability), StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void BuildGhostConciergeJsonReturnsBoundedSplitContract()
    {
        using Fixture fixture = new();

        IActionResult result = fixture.Controller.BuildGhostConciergeJson();

        var ok = Assert.IsType<OkObjectResult>(result);
        using JsonDocument payload = JsonSerializer.SerializeToDocument(ok.Value);
        Assert.Equal("/participate", payload.RootElement.GetProperty("FacePopEntryHref").GetString());
        Assert.Equal("Public concierge only", payload.RootElement.GetProperty("FacePopStatus").GetString());
        Assert.Equal("First-party compare/apply only", payload.RootElement.GetProperty("EngineStatus").GetString());
        Assert.Contains("Short intake", payload.RootElement.GetProperty("CanonicalLane").GetString(), StringComparison.Ordinal);
        Assert.Contains("plain-language explanation", payload.RootElement.GetProperty("CanonicalLane").GetString(), StringComparison.Ordinal);
        Assert.Contains("Neither the public concierge nor the bounded explainer may compute legality", payload.RootElement.GetProperty("RuntimeBoundary").GetString(), StringComparison.Ordinal);
        Assert.True(payload.RootElement.GetProperty("Actions").GetArrayLength() >= 3);
    }

    [Fact]
    public void AliceReceiptJsonReturnsBoundedSplitContract()
    {
        using Fixture fixture = new();

        IActionResult result = fixture.Controller.AliceReceiptJson();

        var ok = Assert.IsType<OkObjectResult>(result);
        using JsonDocument payload = JsonSerializer.SerializeToDocument(ok.Value);
        Assert.Equal("/participate", payload.RootElement.GetProperty("FacePopEntryHref").GetString());
        Assert.Equal("Public concierge only", payload.RootElement.GetProperty("FacePopStatus").GetString());
        Assert.Equal("First-party compare/apply only", payload.RootElement.GetProperty("EngineStatus").GetString());
        Assert.Contains("/account/alice/open", payload.RootElement.GetProperty("Actions").EnumerateArray().Select(item => item.GetProperty("Href").GetString()), StringComparer.Ordinal);
        Assert.Equal("/account/alice", payload.RootElement.GetProperty("SignedInBench").GetProperty("AccountEntryHref").GetString());
        Assert.Equal("/account/alice/open", payload.RootElement.GetProperty("SignedInBench").GetProperty("AccountRedirectHref").GetString());
        Assert.Equal("/api/v1/campaign-spine/me/build-handoffs", payload.RootElement.GetProperty("SignedInBench").GetProperty("HandoffIndexApiHref").GetString());
        Assert.Equal("/api/v1/campaign-spine/me/build-handoffs/{handoffId}", payload.RootElement.GetProperty("SignedInBench").GetProperty("HandoffDetailApiHrefTemplate").GetString());
    }

    [Fact]
    public void TablePulseReceiptJsonReturnsSeparateLiveAndAftermathContract()
    {
        using Fixture fixture = new();

        IActionResult result = fixture.Controller.TablePulseReceiptJson();

        var ok = Assert.IsType<OkObjectResult>(result);
        using JsonDocument payload = JsonSerializer.SerializeToDocument(ok.Value);
        Assert.Equal("table_pulse", payload.RootElement.GetProperty("Horizon").GetString());
        Assert.Equal("shipped_mvp", payload.RootElement.GetProperty("Status").GetString());
        Assert.Equal("pass", payload.RootElement.GetProperty("SeparationStatus").GetString());
        Assert.Equal("/account/ledger/notifications", payload.RootElement.GetProperty("LiveRail").GetProperty("NotificationsHref").GetString());
        Assert.Equal("/account/work#aftermath-packages", payload.RootElement.GetProperty("AftermathRail").GetProperty("WorkspaceHref").GetString());
        Assert.Equal(2, payload.RootElement.GetProperty("AftermathRail").GetProperty("ApiRoutes").GetArrayLength());
        JsonElement sharedArtifacts = payload.RootElement.GetProperty("SharedArtifacts");
        Assert.Equal("/api/v1/public/horizons/capabilities", sharedArtifacts.GetProperty("PublicCapabilityCatalogHref").GetString());
        Assert.Null(sharedArtifacts.GetProperty("PublicCapabilityHealthHref").GetString());
        Assert.Equal("/api/v1/horizons/capabilities/me?horizonId=table-pulse&artifactKindOrCapabilityId=table-pulse-debrief", sharedArtifacts.GetProperty("SignedInCapabilityCatalogHref").GetString());
        Assert.Equal("/api/v1/horizons/quotas/me?horizonId=table-pulse&artifactKindOrCapabilityId=table-pulse-debrief", sharedArtifacts.GetProperty("SignedInQuotaCatalogHref").GetString());
        Assert.Equal("/api/v1/horizons/artifact-requests/me?horizonId=table-pulse", sharedArtifacts.GetProperty("SignedInRequestReceiptHref").GetString());
        Assert.Equal("/api/v1/horizons/artifact-requests/me/{requestId}", sharedArtifacts.GetProperty("SignedInRequestReceiptDetailHrefTemplate").GetString());
        JsonElement capability = payload.RootElement.GetProperty("ArtifactCapability");
        Assert.Equal("table-pulse", capability.GetProperty("HorizonId").GetString());
        Assert.Equal("table-pulse-debrief", capability.GetProperty("CapabilityId").GetString());
        Assert.Equal("debrief_packet", capability.GetProperty("ArtifactKind").GetString());
        Assert.Equal("Debrief Packet", capability.GetProperty("PublicLabel").GetString());
        Assert.Equal("post_session_coaching", capability.GetProperty("CapabilitySlot").GetString());
        Assert.Equal("disabled", capability.GetProperty("Status").GetString());
        Assert.Equal("table-pulse:live-and-aftermath", capability.GetProperty("SourceRef").GetString());
        Assert.DoesNotContain("hedy", JsonSerializer.Serialize(ok.Value), StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("Nonverbia", JsonSerializer.Serialize(ok.Value), StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void OriginDossierReceiptJsonReturnsStoryAndSharedArtifactContract()
    {
        using Fixture fixture = new();

        IActionResult result = fixture.Controller.OriginDossierReceiptJson();

        OkObjectResult ok = Assert.IsType<OkObjectResult>(result);
        using JsonDocument payload = JsonSerializer.SerializeToDocument(ok.Value);
        Assert.Equal("origin-dossier", payload.RootElement.GetProperty("Horizon").GetString());
        Assert.Equal("shipped_mvp", payload.RootElement.GetProperty("Status").GetString());
        Assert.Equal("/docs/origin-dossier-the-name-she-chose", payload.RootElement.GetProperty("PublicBoard").GetProperty("StoryBookletHref").GetString());
        Assert.Equal("/origin-dossier/media", payload.RootElement.GetProperty("PublicBoard").GetProperty("MediaDispatchHref").GetString());
        JsonElement sharedArtifacts = payload.RootElement.GetProperty("SharedArtifacts");
        Assert.Equal("/api/v1/public/horizons/capabilities", sharedArtifacts.GetProperty("PublicCapabilityCatalogHref").GetString());
        Assert.Null(sharedArtifacts.GetProperty("PublicCapabilityHealthHref").GetString());
        Assert.Equal("/api/v1/horizons/capabilities/me?horizonId=origin-dossier&artifactKindOrCapabilityId=origin-dossier-media", sharedArtifacts.GetProperty("SignedInCapabilityCatalogHref").GetString());
        Assert.Equal("/api/v1/horizons/quotas/me?horizonId=origin-dossier&artifactKindOrCapabilityId=origin-dossier-media", sharedArtifacts.GetProperty("SignedInQuotaCatalogHref").GetString());
        Assert.Equal("/api/v1/horizons/artifact-requests/me?horizonId=origin-dossier", sharedArtifacts.GetProperty("SignedInRequestReceiptHref").GetString());
        Assert.Equal("/api/v1/horizons/artifact-requests/me/{requestId}", sharedArtifacts.GetProperty("SignedInRequestReceiptDetailHrefTemplate").GetString());
        JsonElement capability = payload.RootElement.GetProperty("ArtifactCapability");
        Assert.Equal("origin-dossier-media", capability.GetProperty("CapabilityId").GetString());
        Assert.Equal("origin-dossier:public-story-packet", capability.GetProperty("SourceRef").GetString());
        JsonElement boundary = payload.RootElement.GetProperty("Boundary");
        Assert.Equal("approved_chummer_owned_packet", boundary.GetProperty("StoryTruth").GetString());
        Assert.Equal("not_claimed", boundary.GetProperty("SilentMechanicsMutation").GetString());
        Assert.Equal("not_claimed", boundary.GetProperty("ProviderTruth").GetString());
        string serialized = JsonSerializer.Serialize(ok.Value);
        Assert.DoesNotContain("Subscribr", serialized, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("First Book", serialized, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("MarkupGo", serialized, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("vidBoard", serialized, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("source packet", serialized, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("webhook", serialized, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task TablePulsePageIncludesPublicSafeCapabilityMetadata()
    {
        using Fixture fixture = new(configureSettings: settings =>
        {
            settings["CHUMMER_HORIZON_TABLE_PULSE_CAPABILITY_TABLE_PULSE_DEBRIEF_ENABLED"] = "true";
        });
        fixture.Controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };
        fixture.Controller.ControllerContext.HttpContext.Request.Path = "/table-pulse";

        IActionResult result = await fixture.Controller.TablePulsePage(CancellationToken.None);

        ViewResult view = Assert.IsType<ViewResult>(result);
        TrustPageViewModel model = Assert.IsType<TrustPageViewModel>(view.Model);
        Assert.NotNull(model.HorizonCapability);
        Assert.Equal("table-pulse", model.HorizonCapability!.HorizonId);
        Assert.Equal("table-pulse-debrief", model.HorizonCapability.CapabilityId);
        Assert.Equal("available", model.HorizonCapability.Status);
        Assert.True(model.HorizonCapability.RequestSupported);
        Assert.Equal("table-pulse:live-and-aftermath", model.HorizonCapability.SourceRef);
        Assert.Contains(model.Actions, action =>
            action.Label == "Open aftermath"
            && action.Href == "/table-pulse/debrief");
        Assert.DoesNotContain("hedy", JsonSerializer.Serialize(model.HorizonCapability), StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("Nonverbia", JsonSerializer.Serialize(model.HorizonCapability), StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task OriginDossierPageIncludesPublicSafeDossierMediaCapability()
    {
        using Fixture fixture = new(configureSettings: settings =>
        {
            settings["CHUMMER_HORIZON_ORIGIN_DOSSIER_CAPABILITY_ORIGIN_DOSSIER_MEDIA_ENABLED"] = "true";
        });
        fixture.Controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };
        fixture.Controller.ControllerContext.HttpContext.Request.Path = "/origin-dossier";

        IActionResult result = await fixture.Controller.OriginDossierPage(CancellationToken.None);

        ViewResult view = Assert.IsType<ViewResult>(result);
        TrustPageViewModel model = Assert.IsType<TrustPageViewModel>(view.Model);
        Assert.NotNull(model.HorizonCapability);
        Assert.Equal("origin-dossier", model.HorizonCapability!.HorizonId);
        Assert.Equal("origin-dossier-media", model.HorizonCapability.CapabilityId);
        Assert.Equal("dossier_media", model.HorizonCapability.ArtifactKind);
        Assert.Equal("Dossier Media", model.HorizonCapability.PublicLabel);
        Assert.Equal("approved_origin_media", model.HorizonCapability.CapabilitySlot);
        Assert.Equal("available", model.HorizonCapability.Status);
        Assert.True(model.HorizonCapability.RequestSupported);
        Assert.Equal("origin-dossier:public-story-packet", model.HorizonCapability.SourceRef);
        Assert.Contains("story packet", model.Intro, StringComparison.Ordinal);
        Assert.Contains("sheet stays authoritative", model.Intro, StringComparison.Ordinal);
        TrustPageSectionViewModel boundarySection = Assert.Single(model.Sections, section => section.Id == "origin_boundary");
        Assert.Contains("does not get to do", boundarySection.Heading, StringComparison.Ordinal);
        Assert.Contains("does not get to smuggle in ware", boundarySection.Body, StringComparison.Ordinal);
        Assert.Contains(model.Actions, action =>
            action.Label == "Watch the narrated overview"
            && action.Href == "/origin-dossier/media");
        string serialized = JsonSerializer.Serialize(model);
        Assert.DoesNotContain("Subscribr", serialized, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("First Book", serialized, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("MarkupGo", serialized, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("vidBoard", serialized, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("Soundmadeseen", serialized, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("source packet", serialized, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("webhook", serialized, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task OriginDossierDocumentPageIncludesPublicSafeDossierMediaCapability()
    {
        using Fixture fixture = new(configureSettings: settings =>
        {
            settings["CHUMMER_HORIZON_ORIGIN_DOSSIER_CAPABILITY_ORIGIN_DOSSIER_MEDIA_ENABLED"] = "true";
        });
        fixture.Controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };
        fixture.Controller.ControllerContext.HttpContext.Request.Path = "/docs/origin-dossier-the-name-she-chose";

        IActionResult result = await fixture.Controller.DocumentPortalDetailPage("origin-dossier-the-name-she-chose", CancellationToken.None);

        ViewResult view = Assert.IsType<ViewResult>(result);
        TrustPageViewModel model = Assert.IsType<TrustPageViewModel>(view.Model);
        Assert.NotNull(model.HorizonCapability);
        Assert.Equal("origin-dossier-media", model.HorizonCapability!.CapabilityId);
        Assert.Equal("available", model.HorizonCapability.Status);
        Assert.Equal("origin-dossier:document:origin-dossier-the-name-she-chose", model.HorizonCapability.SourceRef);
        string serialized = JsonSerializer.Serialize(model.HorizonCapability);
        Assert.DoesNotContain("First Book", serialized, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("MarkupGo", serialized, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("vidBoard", serialized, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("Soundmadeseen", serialized, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task RunnerPassportReceiptJsonReturnsSignedInContinuityContract()
    {
        using Fixture fixture = new();
        fixture.Controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };

        IActionResult result = await fixture.Controller.RunnerPassportIdentityNetworkReceiptJson(CancellationToken.None);

        var ok = Assert.IsType<OkObjectResult>(result);
        using JsonDocument payload = JsonSerializer.SerializeToDocument(ok.Value);
        Assert.Equal("runner_passport", payload.RootElement.GetProperty("Horizon").GetString());
        Assert.Equal("shipped_mvp", payload.RootElement.GetProperty("Status").GetString());
        Assert.Equal("/passport/runner_return_posture.md", payload.RootElement.GetProperty("PublicBoard").GetProperty("RunnerReturnMarkdownHref").GetString());
        Assert.Equal("/passport/runner_return_posture.json", payload.RootElement.GetProperty("PublicBoard").GetProperty("RunnerReturnJsonHref").GetString());
        Assert.Equal("/account/passport", payload.RootElement.GetProperty("SignedInBench").GetProperty("AccountEntryHref").GetString());
        Assert.Equal("/account/passport/open", payload.RootElement.GetProperty("SignedInBench").GetProperty("AccountRedirectHref").GetString());
        Assert.Equal("/account/ledger/notifications", payload.RootElement.GetProperty("SignedInBench").GetProperty("LiveNotificationsHref").GetString());
        Assert.Equal("/account/work#aftermath-packages", payload.RootElement.GetProperty("SignedInBench").GetProperty("AftermathHref").GetString());
        JsonElement sharedArtifacts = payload.RootElement.GetProperty("SharedArtifacts");
        Assert.Equal("/api/v1/public/horizons/capabilities", sharedArtifacts.GetProperty("PublicCapabilityCatalogHref").GetString());
        Assert.Equal("/api/v1/public/horizons/capabilities?horizonId=runner_passport&artifactKindOrCapabilityId=runner_passport-identity-network", sharedArtifacts.GetProperty("PublicCapabilityHealthHref").GetString());
        Assert.Null(sharedArtifacts.GetProperty("SignedInCapabilityCatalogHref").GetString());
        Assert.Null(sharedArtifacts.GetProperty("SignedInQuotaCatalogHref").GetString());
        Assert.Null(sharedArtifacts.GetProperty("SignedInRequestReceiptHref").GetString());
        Assert.Null(sharedArtifacts.GetProperty("SignedInRequestReceiptDetailHrefTemplate").GetString());
        JsonElement capability = payload.RootElement.GetProperty("ArtifactCapability");
        Assert.Equal("runner_passport", capability.GetProperty("HorizonId").GetString());
        Assert.Equal("runner_passport-identity-network", capability.GetProperty("CapabilityId").GetString());
        Assert.Equal("identity_network", capability.GetProperty("ArtifactKind").GetString());
        Assert.Equal("Identity Network", capability.GetProperty("PublicLabel").GetString());
        Assert.Equal("public_identity_return", capability.GetProperty("CapabilitySlot").GetString());
        Assert.Equal("available", capability.GetProperty("Status").GetString());
        Assert.True(capability.GetProperty("RequestSupported").GetBoolean());
        Assert.False(capability.GetProperty("QuotaTracked").GetBoolean());
        Assert.Equal("runner_passport:identity-network", capability.GetProperty("SourceRef").GetString());
        string requestId = fixture.Controller.Response.Headers["X-Horizon-Artifact-Request-Id"].ToString();
        Assert.StartsWith("horizon-artifact-", requestId, StringComparison.Ordinal);
        Assert.Equal($"/api/v1/public/horizons/artifact-requests/{requestId}", fixture.Controller.Response.Headers["X-Horizon-Artifact-Request-Href"].ToString());
    }

    [Fact]
    public async Task CommunityHubReceiptJsonReturnsSharedOpenRunContract()
    {
        using Fixture fixture = new();
        fixture.Controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };

        IActionResult result = await fixture.Controller.CommunityHubReceiptJson(CancellationToken.None);

        var ok = Assert.IsType<OkObjectResult>(result);
        using JsonDocument payload = JsonSerializer.SerializeToDocument(ok.Value);
        Assert.Equal("community_hub", payload.RootElement.GetProperty("Horizon").GetString());
        Assert.Equal("shipped_mvp", payload.RootElement.GetProperty("Status").GetString());
        Assert.Equal("/community/open-runs/open_run_board.md", payload.RootElement.GetProperty("PublicBoard").GetProperty("BoardMarkdownHref").GetString());
        Assert.Equal("/community/open-runs/open_run_board.json", payload.RootElement.GetProperty("PublicBoard").GetProperty("BoardJsonHref").GetString());
        Assert.Equal("/account/community", payload.RootElement.GetProperty("SignedInBench").GetProperty("AccountEntryHref").GetString());
        Assert.Equal("/account/community/open", payload.RootElement.GetProperty("SignedInBench").GetProperty("AccountRedirectHref").GetString());
        JsonElement sharedArtifacts = payload.RootElement.GetProperty("SharedArtifacts");
        Assert.Equal("/api/v1/public/horizons/capabilities?horizonId=community_hub&artifactKindOrCapabilityId=community_hub-open-run-network", sharedArtifacts.GetProperty("PublicCapabilityHealthHref").GetString());
        Assert.Null(sharedArtifacts.GetProperty("SignedInCapabilityCatalogHref").GetString());
        JsonElement capability = payload.RootElement.GetProperty("ArtifactCapability");
        Assert.Equal("community_hub-open-run-network", capability.GetProperty("CapabilityId").GetString());
        Assert.Equal("open_run_network", capability.GetProperty("ArtifactKind").GetString());
        Assert.False(capability.GetProperty("QuotaTracked").GetBoolean());
        Assert.Equal("community_hub:open-run-network", capability.GetProperty("SourceRef").GetString());
        string requestId = fixture.Controller.Response.Headers["X-Horizon-Artifact-Request-Id"].ToString();
        Assert.StartsWith("horizon-artifact-", requestId, StringComparison.Ordinal);
        Assert.Equal($"/api/v1/public/horizons/artifact-requests/{requestId}", fixture.Controller.Response.Headers["X-Horizon-Artifact-Request-Href"].ToString());
    }

    [Fact]
    public async Task CreatorOsReceiptJsonReturnsSharedPublicationContract()
    {
        using Fixture fixture = new();
        fixture.Controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };

        IActionResult result = await fixture.Controller.CreatorOsReceiptJson(CancellationToken.None);

        var ok = Assert.IsType<OkObjectResult>(result);
        using JsonDocument payload = JsonSerializer.SerializeToDocument(ok.Value);
        Assert.Equal("creator_os", payload.RootElement.GetProperty("Horizon").GetString());
        Assert.Equal("shipped_mvp", payload.RootElement.GetProperty("Status").GetString());
        Assert.Equal("/creator/packets/publication_board.md", payload.RootElement.GetProperty("PublicBoard").GetProperty("BoardMarkdownHref").GetString());
        Assert.Equal("/creator/packets/publication_board.json", payload.RootElement.GetProperty("PublicBoard").GetProperty("BoardJsonHref").GetString());
        Assert.Equal("/account/creator", payload.RootElement.GetProperty("SignedInBench").GetProperty("AccountEntryHref").GetString());
        Assert.Equal("/account/creator/open", payload.RootElement.GetProperty("SignedInBench").GetProperty("AccountRedirectHref").GetString());
        JsonElement sharedArtifacts = payload.RootElement.GetProperty("SharedArtifacts");
        Assert.Equal("/api/v1/public/horizons/capabilities?horizonId=creator_os&artifactKindOrCapabilityId=creator_os-publication-network", sharedArtifacts.GetProperty("PublicCapabilityHealthHref").GetString());
        Assert.Null(sharedArtifacts.GetProperty("SignedInCapabilityCatalogHref").GetString());
        JsonElement capability = payload.RootElement.GetProperty("ArtifactCapability");
        Assert.Equal("creator_os-publication-network", capability.GetProperty("CapabilityId").GetString());
        Assert.Equal("publication_network", capability.GetProperty("ArtifactKind").GetString());
        Assert.False(capability.GetProperty("QuotaTracked").GetBoolean());
        Assert.Equal("creator_os:publication-network", capability.GetProperty("SourceRef").GetString());
        string requestId = fixture.Controller.Response.Headers["X-Horizon-Artifact-Request-Id"].ToString();
        Assert.StartsWith("horizon-artifact-", requestId, StringComparison.Ordinal);
        Assert.Equal($"/api/v1/public/horizons/artifact-requests/{requestId}", fixture.Controller.Response.Headers["X-Horizon-Artifact-Request-Href"].ToString());
    }

    [Fact]
    public void JackpointReceiptJsonReturnsSignedInPublicationContract()
    {
        using Fixture fixture = new();

        IActionResult result = fixture.Controller.JackpointReceiptJson();

        var ok = Assert.IsType<OkObjectResult>(result);
        using JsonDocument payload = JsonSerializer.SerializeToDocument(ok.Value);
        Assert.Equal("jackpoint", payload.RootElement.GetProperty("Horizon").GetString());
        Assert.Equal("shipped_mvp", payload.RootElement.GetProperty("Status").GetString());
        Assert.Equal("/jackpoint/briefings/emerald-sprawl-briefing.md", payload.RootElement.GetProperty("PublicBoard").GetProperty("FirstBriefingMarkdownHref").GetString());
        Assert.Equal("/jackpoint/briefings/emerald-sprawl-briefing.json", payload.RootElement.GetProperty("PublicBoard").GetProperty("FirstBriefingJsonHref").GetString());
        Assert.Equal("/account/jackpoint", payload.RootElement.GetProperty("SignedInDesk").GetProperty("AccountEntryHref").GetString());
        Assert.Equal("/account/jackpoint/open", payload.RootElement.GetProperty("SignedInDesk").GetProperty("AccountRedirectHref").GetString());
        Assert.Equal("/api/v1/campaign-spine/me/publications", payload.RootElement.GetProperty("SignedInDesk").GetProperty("PublicationIndexApiHref").GetString());
        Assert.Equal("/api/v1/campaign-spine/me/publications/{publicationId}", payload.RootElement.GetProperty("SignedInDesk").GetProperty("PublicationDetailApiHrefTemplate").GetString());
        JsonElement sharedArtifacts = payload.RootElement.GetProperty("SharedArtifacts");
        Assert.Equal("/api/v1/public/horizons/capabilities", sharedArtifacts.GetProperty("PublicCapabilityCatalogHref").GetString());
        Assert.Null(sharedArtifacts.GetProperty("PublicCapabilityHealthHref").GetString());
        Assert.Equal("/api/v1/horizons/capabilities/me?horizonId=jackpoint&artifactKindOrCapabilityId=jackpoint-briefing-video", sharedArtifacts.GetProperty("SignedInCapabilityCatalogHref").GetString());
        Assert.Equal("/api/v1/horizons/quotas/me?horizonId=jackpoint&artifactKindOrCapabilityId=jackpoint-briefing-video", sharedArtifacts.GetProperty("SignedInQuotaCatalogHref").GetString());
        Assert.Equal("/api/v1/horizons/artifact-requests/me?horizonId=jackpoint", sharedArtifacts.GetProperty("SignedInRequestReceiptHref").GetString());
        Assert.Equal("/api/v1/horizons/artifact-requests/me/{requestId}", sharedArtifacts.GetProperty("SignedInRequestReceiptDetailHrefTemplate").GetString());
        JsonElement capability = payload.RootElement.GetProperty("ArtifactCapability");
        Assert.Equal("jackpoint", capability.GetProperty("HorizonId").GetString());
        Assert.Equal("jackpoint-briefing-video", capability.GetProperty("CapabilityId").GetString());
        Assert.Equal("jackpoint:briefing-network", capability.GetProperty("SourceRef").GetString());
        Assert.DoesNotContain("vidBoard", JsonSerializer.Serialize(ok.Value), StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void RunbookReceiptJsonReturnsPrimerAndSharedArtifactContract()
    {
        using Fixture fixture = new();

        IActionResult result = fixture.Controller.RunbookReceiptJson();

        OkObjectResult ok = Assert.IsType<OkObjectResult>(result);
        using JsonDocument payload = JsonSerializer.SerializeToDocument(ok.Value);
        Assert.Equal("runbook-press", payload.RootElement.GetProperty("Horizon").GetString());
        Assert.Equal("shipped_mvp", payload.RootElement.GetProperty("Status").GetString());
        Assert.Equal("/runbook/primers/new-runner-primer.md", payload.RootElement.GetProperty("PublicBoard").GetProperty("FirstPrimerMarkdownHref").GetString());
        Assert.Equal("/runbook/primers/{primerId}/export", payload.RootElement.GetProperty("PublicBoard").GetProperty("ExportDispatchHrefTemplate").GetString());
        JsonElement sharedArtifacts = payload.RootElement.GetProperty("SharedArtifacts");
        Assert.Equal("/api/v1/public/horizons/capabilities", sharedArtifacts.GetProperty("PublicCapabilityCatalogHref").GetString());
        Assert.Null(sharedArtifacts.GetProperty("PublicCapabilityHealthHref").GetString());
        Assert.Equal("/api/v1/horizons/capabilities/me?horizonId=runbook-press&artifactKindOrCapabilityId=runbook-export", sharedArtifacts.GetProperty("SignedInCapabilityCatalogHref").GetString());
        Assert.Equal("/api/v1/horizons/quotas/me?horizonId=runbook-press&artifactKindOrCapabilityId=runbook-export", sharedArtifacts.GetProperty("SignedInQuotaCatalogHref").GetString());
        Assert.Equal("/api/v1/horizons/artifact-requests/me?horizonId=runbook-press", sharedArtifacts.GetProperty("SignedInRequestReceiptHref").GetString());
        Assert.Equal("/api/v1/horizons/artifact-requests/me/{requestId}", sharedArtifacts.GetProperty("SignedInRequestReceiptDetailHrefTemplate").GetString());
        JsonElement capability = payload.RootElement.GetProperty("ArtifactCapability");
        Assert.Equal("runbook-export", capability.GetProperty("CapabilityId").GetString());
        Assert.Equal("runbook-press:primer-network", capability.GetProperty("SourceRef").GetString());
        JsonElement boundary = payload.RootElement.GetProperty("Boundary");
        Assert.Equal("not_claimed", boundary.GetProperty("PublicationStudio").GetString());
        Assert.Equal("chummer_owned_primer_packets", boundary.GetProperty("SourceTruth").GetString());
        Assert.Equal("not_claimed", boundary.GetProperty("ProviderTruth").GetString());
        string serialized = JsonSerializer.Serialize(ok.Value);
        Assert.DoesNotContain("Subscribr", serialized, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("First Book", serialized, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("MarkupGo", serialized, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("Documentation.AI", serialized, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("source packet", serialized, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("webhook", serialized, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task RunbookPageKeepsPublicCopyProviderNeutralAndBoundarySafe()
    {
        using Fixture fixture = new();
        fixture.Controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };
        fixture.Controller.ControllerContext.HttpContext.Request.Path = "/runbook";

        IActionResult result = await fixture.Controller.RunbookPreviewPage(CancellationToken.None);

        ViewResult view = Assert.IsType<ViewResult>(result);
        MediaArtifactHorizonPageViewModel model = Assert.IsType<MediaArtifactHorizonPageViewModel>(view.Model);
        Assert.Equal("RUNBOOK PRESS", model.Heading);
        Assert.Equal("RUNBOOK PRESS now ships real primers: guides you can hand to a player or GM without sending them into scattered docs.", model.Intro);
        Assert.Equal("Printable onboarding and prep guides only. This path does not claim a full long-form publication studio yet.", model.BoundaryLine);
        Assert.Contains(model.SummaryPoints, point => point == "Printable guides");
        Assert.Equal("/runbook/primers/new-runner-primer.md", model.PrimaryAction.Href);
        Assert.Equal("/runbook/primers/new-runner-primer.json", model.SecondaryAction.Href);
        Assert.Contains(model.Documents, document =>
            document.MarkdownRoute == "/runbook/primers/new-runner-primer.md"
            && document.JsonRoute == "/runbook/primers/new-runner-primer.json");
        string serialized = JsonSerializer.Serialize(model);
        Assert.DoesNotContain("Subscribr", serialized, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("First Book", serialized, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("MarkupGo", serialized, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("Documentation.AI", serialized, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("source packet", serialized, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("webhook", serialized, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void RunsitePackJsonIncludesStyleAndTourActionFields()
    {
        using Fixture fixture = new();

        IActionResult result = fixture.Controller.RunsitePackJson("redmond-dockyard-pack");

        var content = Assert.IsType<ContentResult>(result);
        using JsonDocument payload = JsonDocument.Parse(content.Content ?? "{}");
        Assert.Equal("Research Lab", payload.RootElement.GetProperty("style").GetString());
        Assert.Equal("/runsites/packs/redmond-dockyard-pack/tour", payload.RootElement.GetProperty("tour_action_href").GetString());
        Assert.Equal("Open 3D Tour", payload.RootElement.GetProperty("tour_action_label").GetString());
        Assert.False(payload.RootElement.GetProperty("tour_action_open_in_new_tab").GetBoolean());
        Assert.Equal("/runsites/packs/redmond-dockyard-pack/tour", payload.RootElement.GetProperty("tour_href").GetString());
        Assert.False(payload.RootElement.GetProperty("tour_open_in_new_tab").GetBoolean());
        Assert.Equal("3D Tour", payload.RootElement.GetProperty("tour_label").GetString());
    }

    [Fact]
    public void JackpointBriefingJsonIncludesStyleAndActionFields()
    {
        using Fixture fixture = new();

        IActionResult result = fixture.Controller.JackpointBriefingJson("emerald-sprawl-briefing");

        var content = Assert.IsType<ContentResult>(result);
        using JsonDocument payload = JsonDocument.Parse(content.Content ?? "{}");
        Assert.Equal("Dossier", payload.RootElement.GetProperty("style").GetString());
        Assert.Equal("/jackpoint/briefings/emerald-sprawl-briefing/video", payload.RootElement.GetProperty("tour_action_href").GetString());
        Assert.Equal("Open Briefing Video", payload.RootElement.GetProperty("tour_action_label").GetString());
        Assert.False(payload.RootElement.GetProperty("tour_action_open_in_new_tab").GetBoolean());
        Assert.Equal("/jackpoint/briefings/emerald-sprawl-briefing/video", payload.RootElement.GetProperty("tour_href").GetString());
        Assert.Equal("Briefing Video", payload.RootElement.GetProperty("artifact_capability").GetProperty("public_label").GetString());
    }

    [Fact]
    public void RunbookPrimerJsonIncludesStyleAndActionFields()
    {
        using Fixture fixture = new();

        IActionResult result = fixture.Controller.RunbookPrimerJson("new-runner-primer");

        var content = Assert.IsType<ContentResult>(result);
        using JsonDocument payload = JsonDocument.Parse(content.Content ?? "{}");
        Assert.Equal("Primer", payload.RootElement.GetProperty("style").GetString());
        Assert.Equal("/runbook/primers/new-runner-primer/export", payload.RootElement.GetProperty("tour_action_href").GetString());
        Assert.Equal("Export Primer", payload.RootElement.GetProperty("tour_action_label").GetString());
        Assert.False(payload.RootElement.GetProperty("tour_action_open_in_new_tab").GetBoolean());
        Assert.Equal("/runbook/primers/new-runner-primer/export", payload.RootElement.GetProperty("tour_href").GetString());
    }

    [Fact]
    public void PropertyquarryPropertyJsonIncludesStyleAndActionFields()
    {
        using Fixture fixture = new();

        IActionResult result = fixture.Controller.PropertyquarryPropertyJson("northbound-research-lab");

        var content = Assert.IsType<ContentResult>(result);
        using JsonDocument payload = JsonDocument.Parse(content.Content ?? "{}");
        Assert.Equal("Research Lab", payload.RootElement.GetProperty("style").GetString());
        Assert.Equal("/propertyquarry/properties/northbound-research-lab/tour", payload.RootElement.GetProperty("tour_action_href").GetString());
        Assert.Equal("Open 3D Tour", payload.RootElement.GetProperty("tour_action_label").GetString());
        Assert.False(payload.RootElement.GetProperty("tour_action_open_in_new_tab").GetBoolean());
        Assert.Equal("/propertyquarry/properties/northbound-research-lab/tour", payload.RootElement.GetProperty("tour_href").GetString());
        Assert.False(payload.RootElement.GetProperty("tour_open_in_new_tab").GetBoolean());
        Assert.Equal("3D Tour", payload.RootElement.GetProperty("tour_label").GetString());
    }

    [Fact]
    public void JackpointBriefingJsonIncludesPublicSafeSharedCapabilityMetadata()
    {
        using Fixture fixture = new();

        IActionResult result = fixture.Controller.JackpointBriefingJson("emerald-sprawl-briefing");

        var content = Assert.IsType<ContentResult>(result);
        using JsonDocument payload = JsonDocument.Parse(content.Content ?? "{}");
        JsonElement capability = payload.RootElement.GetProperty("artifact_capability");
        Assert.Equal("jackpoint", capability.GetProperty("horizon_id").GetString());
        Assert.Equal("jackpoint-briefing-video", capability.GetProperty("capability_id").GetString());
        Assert.Equal("briefing_video", capability.GetProperty("artifact_kind").GetString());
        Assert.Equal("Briefing Video", capability.GetProperty("public_label").GetString());
        Assert.Equal("presenter_video", capability.GetProperty("capability_slot").GetString());
        Assert.Equal("disabled", capability.GetProperty("status").GetString());
        Assert.False(capability.GetProperty("request_supported").GetBoolean());
        Assert.Equal("jackpoint:emerald-sprawl-briefing", capability.GetProperty("source_ref").GetString());
        Assert.False(capability.TryGetProperty("internal_provider_lane", out _));
        Assert.DoesNotContain("vidBoard", content.Content ?? string.Empty, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void PropertyquarryPropertyJsonIncludesPublicSafeSharedCapabilityMetadata()
    {
        using Fixture fixture = new(configureSettings: settings =>
        {
            settings["CHUMMER_HORIZON_PROPERTYQUARRY_CAPABILITY_PROPERTYQUARRY_TOUR_ENABLED"] = "true";
        });

        IActionResult result = fixture.Controller.PropertyquarryPropertyJson("northbound-research-lab");

        var content = Assert.IsType<ContentResult>(result);
        using JsonDocument payload = JsonDocument.Parse(content.Content ?? "{}");
        JsonElement capability = payload.RootElement.GetProperty("artifact_capability");
        Assert.Equal("propertyquarry", capability.GetProperty("horizon_id").GetString());
        Assert.Equal("propertyquarry-tour", capability.GetProperty("capability_id").GetString());
        Assert.Equal("tour", capability.GetProperty("artifact_kind").GetString());
        Assert.Equal("3D Tour", capability.GetProperty("public_label").GetString());
        Assert.Equal("explorable_location", capability.GetProperty("capability_slot").GetString());
        Assert.Equal("available", capability.GetProperty("status").GetString());
        Assert.True(capability.GetProperty("request_supported").GetBoolean());
        Assert.Equal("propertyquarry:northbound-research-lab", capability.GetProperty("source_ref").GetString());
        Assert.False(capability.TryGetProperty("internal_provider_lane", out _));
        Assert.DoesNotContain("Matterport", JsonSerializer.Serialize(capability), StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void RunbookPrimerJsonIncludesPublicSafeSharedCapabilityMetadata()
    {
        using Fixture fixture = new(configureSettings: settings =>
        {
            settings["CHUMMER_HORIZON_RUNBOOK_PRESS_CAPABILITY_RUNBOOK_EXPORT_ENABLED"] = "true";
        });

        IActionResult result = fixture.Controller.RunbookPrimerJson("new-runner-primer");

        var content = Assert.IsType<ContentResult>(result);
        using JsonDocument payload = JsonDocument.Parse(content.Content ?? "{}");
        JsonElement capability = payload.RootElement.GetProperty("artifact_capability");
        Assert.Equal("runbook-press", capability.GetProperty("horizon_id").GetString());
        Assert.Equal("runbook-export", capability.GetProperty("capability_id").GetString());
        Assert.Equal("document_export", capability.GetProperty("artifact_kind").GetString());
        Assert.Equal("Formatted Export", capability.GetProperty("public_label").GetString());
        Assert.Equal("document_render", capability.GetProperty("capability_slot").GetString());
        Assert.Equal("available", capability.GetProperty("status").GetString());
        Assert.True(capability.GetProperty("request_supported").GetBoolean());
        Assert.True(capability.GetProperty("quota_tracked").GetBoolean());
        Assert.Equal("runbook-press:new-runner-primer", capability.GetProperty("source_ref").GetString());
        Assert.DoesNotContain("MarkupGo", JsonSerializer.Serialize(capability), StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task SignalDeckReceiptJsonIncludesPublicSafeSharedCapabilityMetadata()
    {
        using Fixture fixture = new();
        fixture.Controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };

        IActionResult result = await fixture.Controller.SignalDeckReceiptJson("pressure_posture", CancellationToken.None);

        var content = Assert.IsType<ContentResult>(result);
        using JsonDocument payload = JsonDocument.Parse(content.Content ?? "{}");
        JsonElement capability = payload.RootElement.GetProperty("artifact_capability");
        Assert.Equal("signal_deck", capability.GetProperty("horizon_id").GetString());
        Assert.Equal("signal_deck-command-network", capability.GetProperty("capability_id").GetString());
        Assert.Equal("command_network", capability.GetProperty("artifact_kind").GetString());
        Assert.Equal("Command Network", capability.GetProperty("public_label").GetString());
        Assert.Equal("public_command_pressure", capability.GetProperty("capability_slot").GetString());
        Assert.Equal("available", capability.GetProperty("status").GetString());
        Assert.True(capability.GetProperty("request_supported").GetBoolean());
        Assert.False(capability.GetProperty("requires_authentication").GetBoolean());
        Assert.True(capability.GetProperty("public_visible").GetBoolean());
        Assert.False(capability.GetProperty("quota_tracked").GetBoolean());
        Assert.Equal("signal_deck:pressure_posture", capability.GetProperty("source_ref").GetString());
        string requestId = fixture.Controller.Response.Headers["X-Horizon-Artifact-Request-Id"].ToString();
        Assert.StartsWith("horizon-artifact-", requestId, StringComparison.Ordinal);
        Assert.Equal($"/api/v1/public/horizons/artifact-requests/{requestId}", fixture.Controller.Response.Headers["X-Horizon-Artifact-Request-Href"].ToString());
    }

    [Fact]
    public async Task LivingWorldReceiptJsonIncludesPublicSafeSharedCapabilityMetadata()
    {
        using Fixture fixture = new();
        fixture.Controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };

        IActionResult result = await fixture.Controller.LivingWorldReceiptJson("watch_package_posture", CancellationToken.None);

        var content = Assert.IsType<ContentResult>(result);
        using JsonDocument payload = JsonDocument.Parse(content.Content ?? "{}");
        JsonElement capability = payload.RootElement.GetProperty("artifact_capability");
        Assert.Equal("living_world", capability.GetProperty("horizon_id").GetString());
        Assert.Equal("living_world-watch-network", capability.GetProperty("capability_id").GetString());
        Assert.Equal("watch_network", capability.GetProperty("artifact_kind").GetString());
        Assert.Equal("Watch Network", capability.GetProperty("public_label").GetString());
        Assert.Equal("public_world_watch", capability.GetProperty("capability_slot").GetString());
        Assert.Equal("available", capability.GetProperty("status").GetString());
        Assert.True(capability.GetProperty("request_supported").GetBoolean());
        Assert.False(capability.GetProperty("requires_authentication").GetBoolean());
        Assert.True(capability.GetProperty("public_visible").GetBoolean());
        Assert.False(capability.GetProperty("quota_tracked").GetBoolean());
        Assert.Equal("living_world:watch_package_posture", capability.GetProperty("source_ref").GetString());
        string requestId = fixture.Controller.Response.Headers["X-Horizon-Artifact-Request-Id"].ToString();
        Assert.StartsWith("horizon-artifact-", requestId, StringComparison.Ordinal);
        Assert.Equal($"/api/v1/public/horizons/artifact-requests/{requestId}", fixture.Controller.Response.Headers["X-Horizon-Artifact-Request-Href"].ToString());
    }

    [Fact]
    public async Task CommunityCreatorReceiptJsonRoutesReturnNotFoundForUnknownIds()
    {
        using Fixture fixture = new();

        Assert.IsType<NotFoundResult>(await fixture.Controller.CommunityOpenRunPacketJson("unknown-packet", CancellationToken.None));
        Assert.IsType<NotFoundResult>(await fixture.Controller.CreatorPacketJson("unknown-packet", CancellationToken.None));
        Assert.IsType<NotFoundResult>(await fixture.Controller.PassportReceiptJson("unknown-receipt", CancellationToken.None));
        Assert.IsType<NotFoundResult>(await fixture.Controller.SignalDeckReceiptJson("unknown-receipt", CancellationToken.None));
        Assert.IsType<NotFoundResult>(await fixture.Controller.LivingWorldReceiptJson("unknown-receipt", CancellationToken.None));
    }

    [Fact]
    public void RunsitePacksCanUseWhiteLabeledTourConfig()
    {
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["RunsiteTour:Href"] = "https://3dvista.example.test/tour/abc",
                ["RunsiteTour:Label"] = "3DVista Tour",
                ["RunsiteTour:ActionLabel"] = "Launch 3DVista",
                ["RunsiteTour:OpenInNewTab"] = "false"
            })
            .Build();

        MediaArtifactHorizonsService mediaHorizons = new(configuration);
        MediaArtifactDocument firstPack = mediaHorizons.GetRunsitePack("redmond-dockyard-pack");

        Assert.Equal("/runsites/packs/redmond-dockyard-pack/tour", firstPack.TourHref);
        Assert.Equal("3DVista Tour", firstPack.TourLabel);
        Assert.False(firstPack.TourOpenInNewTab);
        Assert.Equal("/runsites/packs/redmond-dockyard-pack/tour", firstPack.TourActionHref);
        Assert.Equal("Launch 3DVista", firstPack.TourActionLabel);
        Assert.False(firstPack.TourActionOpenInNewTab);
        Assert.Equal("https://3dvista.example.test/tour/abc", firstPack.DispatchTargetHref);
    }

    [Fact]
    public void PropertyquarryPropertiesCanUseWhiteLabeledTourConfig()
    {
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["PropertyquarryTour:Href"] = "https://3dvista.example.test/tour/pq",
                ["PropertyquarryTour:Label"] = "3DVista Property Tour",
                ["PropertyquarryTour:ActionLabel"] = "Open Property 3DVista",
                ["PropertyquarryTour:OpenInNewTab"] = "false"
            })
            .Build();

        MediaArtifactHorizonsService mediaHorizons = new(configuration);
        MediaArtifactDocument firstProperty = mediaHorizons.GetPropertyquarryProperty("northbound-research-lab");

        Assert.Equal("/propertyquarry/properties/northbound-research-lab/tour", firstProperty.TourHref);
        Assert.Equal("3DVista Property Tour", firstProperty.TourLabel);
        Assert.False(firstProperty.TourOpenInNewTab);
        Assert.Equal("/propertyquarry/properties/northbound-research-lab/tour", firstProperty.TourActionHref);
        Assert.Equal("Open Property 3DVista", firstProperty.TourActionLabel);
        Assert.False(firstProperty.TourActionOpenInNewTab);
        Assert.Equal("https://3dvista.example.test/tour/pq", firstProperty.DispatchTargetHref);
    }

    [Fact]
    public void SharedSpatialTourStyleConfigCanDriveRunsiteAndPropertyquarryTogether()
    {
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["SpatialTours:ProviderPreference"] = "3dvista",
                ["SpatialTours:Styles:ResearchLab:3DVistaHref"] = "https://3dvista.example.test/tours/research-lab",
                ["SpatialTours:Styles:ResearchLab:Label"] = "Lab Tour"
            })
            .Build();

        MediaArtifactHorizonsService mediaHorizons = new(configuration);
        MediaArtifactDocument runsitePack = mediaHorizons.GetRunsitePack("redmond-dockyard-pack");
        MediaArtifactDocument property = mediaHorizons.GetPropertyquarryProperty("northbound-research-lab");

        Assert.Equal("https://3dvista.example.test/tours/research-lab", runsitePack.DispatchTargetHref);
        Assert.Equal("Lab Tour", runsitePack.TourLabel);
        Assert.Equal("Open Lab Tour", runsitePack.TourActionLabel);
        Assert.Equal(runsitePack.DispatchTargetHref, property.DispatchTargetHref);
        Assert.Equal(runsitePack.TourLabel, property.TourLabel);
        Assert.Equal(runsitePack.TourActionLabel, property.TourActionLabel);
    }

    [Fact]
    public void SharedSpatialTourCatalogUsesStyleAwareBuiltInTargets()
    {
        MediaArtifactHorizonsService mediaHorizons = new();

        MediaArtifactDocument officeRunsite = mediaHorizons.GetRunsitePack("everett-switchyard-pack");
        MediaArtifactDocument factoryProperty = mediaHorizons.GetPropertyquarryProperty("shoreline-automation-factory");
        MediaArtifactDocument officeProperty = mediaHorizons.GetPropertyquarryProperty("eastriver-office-hub");

        Assert.Equal("https://www.3dvista.com/samples/new_york_loft.html", officeRunsite.DispatchTargetHref);
        Assert.Equal("https://my.matterport.com/show/?m=ax2JhiPGk5P&play=1", factoryProperty.DispatchTargetHref);
        Assert.Equal("https://www.3dvista.com/samples/new_york_loft.html", officeProperty.DispatchTargetHref);
    }

    [Fact]
    public void RunsitePacksIgnoreBlankWhiteLabelConfigAndKeepDefaults()
    {
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["RunsiteTour:Href"] = "  ",
                ["RunsiteTour:Label"] = "",
                ["RunsiteTour:ActionLabel"] = " \t ",
                ["RunsiteTour:OpenInNewTab"] = "not-bool"
            })
            .Build();

        MediaArtifactHorizonsService mediaHorizons = new(configuration);
        MediaArtifactDocument firstPack = mediaHorizons.GetRunsitePack("redmond-dockyard-pack");

        Assert.Equal("/runsites/packs/redmond-dockyard-pack/tour", firstPack.TourHref);
        Assert.Equal("3D Tour", firstPack.TourLabel);
        Assert.Equal("Open 3D Tour", firstPack.TourActionLabel);
        Assert.False(firstPack.TourOpenInNewTab);
        Assert.Equal("https://my.matterport.com/show/?m=ax2JhiPGk5P", firstPack.DispatchTargetHref);
    }

    [Fact]
    public void RunsitePacksExposeDistinctStyles()
    {
        using Fixture fixture = new();

        IActionResult firstPackResult = fixture.Controller.RunsitePackJson("redmond-dockyard-pack");
        IActionResult secondPackResult = fixture.Controller.RunsitePackJson("everett-switchyard-pack");

        using JsonDocument firstPackPayload = JsonDocument.Parse(Assert.IsType<ContentResult>(firstPackResult).Content ?? "{}");
        using JsonDocument secondPackPayload = JsonDocument.Parse(Assert.IsType<ContentResult>(secondPackResult).Content ?? "{}");
        string? firstStyle = firstPackPayload.RootElement.GetProperty("style").GetString();
        string? secondStyle = secondPackPayload.RootElement.GetProperty("style").GetString();
        Assert.Equal("Research Lab", firstStyle);
        Assert.Equal("Office Building", secondStyle);
        Assert.NotEqual(firstStyle, secondStyle);
    }

    [Fact]
    public void HorizonCapabilityHealthPublicSafeDoesNotExposeProviderLane()
    {
        using Fixture fixture = new();
        HorizonCapabilityService capabilities = new(fixture.Configuration);

        HorizonCapabilityHealthSnapshot internalHealth = capabilities.GetHealth("runsite", "tour", publicSafe: false);
        HorizonCapabilityHealthSnapshot publicSafeHealth = capabilities.GetHealth("runsite", "tour", publicSafe: true);

        Assert.Equal("available", internalHealth.Status);
        Assert.Contains("Matterport", internalHealth.InternalProviderLane, StringComparison.OrdinalIgnoreCase);
        Assert.Null(publicSafeHealth.InternalProviderLane);
        Assert.Equal("3D Tour", publicSafeHealth.PublicLabel);
        Assert.Equal(1, publicSafeHealth.FreeWeeklyLimit);
        Assert.Equal(10, publicSafeHealth.SupporterWeeklyLimit);
        Assert.True(publicSafeHealth.QuotaTracked);
    }

    [Fact]
    public void HorizonCapabilityHealthMarksReceiptOnlyCapabilitiesAsNonQuotaTracked()
    {
        using Fixture fixture = new();
        HorizonCapabilityService capabilities = new(fixture.Configuration);

        HorizonCapabilityHealthSnapshot health = capabilities.GetHealth("runner_passport", "identity_network", publicSafe: true);

        Assert.Equal("available", health.Status);
        Assert.False(health.RequiresAuthentication);
        Assert.True(health.PublicVisible);
        Assert.False(health.QuotaTracked);
    }

    [Fact]
    public void EnvironmentExampleDocumentsEveryBuiltInHorizonCapabilityOverride()
    {
        using Fixture fixture = new();
        HorizonCapabilityService capabilities = new(fixture.Configuration);
        string envExample = File.ReadAllText(Path.Combine(RepoPaths.Root, ".env.example"));

        foreach (HorizonCapabilityDefinition capability in capabilities.ListCapabilities())
        {
            string envPrefix =
                $"CHUMMER_HORIZON_{NormalizeHorizonCapabilityEnvToken(capability.HorizonId)}_CAPABILITY_{NormalizeHorizonCapabilityEnvToken(capability.CapabilityId)}";

            Assert.Contains($"{envPrefix}_ENABLED=", envExample, StringComparison.Ordinal);
            Assert.Contains($"{envPrefix}_FREE_WEEKLY_LIMIT=", envExample, StringComparison.Ordinal);
            Assert.Contains($"{envPrefix}_SUPPORTER_WEEKLY_LIMIT=", envExample, StringComparison.Ordinal);
        }
    }

    [Fact]
    public void HorizonArtifactRequestModelBlocksDisabledCapabilityAndMissingConsent()
    {
        using Fixture fixture = new();
        HorizonArtifactRequestService requests = new(new HorizonCapabilityService(fixture.Configuration));

        HorizonArtifactRequestReceipt receipt = requests.BuildRequest(
            new HorizonArtifactRequestCreateRequest(
                HorizonId: "jackpoint",
                ArtifactKindOrCapabilityId: "briefing_video",
                UserId: "subject.dispatch",
                SourceRef: "jackpoint:emerald-sprawl-briefing",
                Visibility: "public_safe",
                ExternalProcessingConsent: false),
            new DateTimeOffset(2026, 6, 26, 10, 0, 0, TimeSpan.Zero));

        Assert.Equal("blocked", receipt.Status);
        Assert.Equal("jackpoint", receipt.HorizonId);
        Assert.Equal("briefing_video", receipt.ArtifactKind);
        Assert.Contains("capability enabled", receipt.BlockedReasons);
        Assert.Contains("external processing consent", receipt.BlockedReasons);
    }

    [Fact]
    public void HorizonArtifactRequestModelAcceptsEnabledJackpointCapabilityWithConsent()
    {
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_HORIZON_JACKPOINT_CAPABILITY_JACKPOINT_BRIEFING_VIDEO_ENABLED"] = "true"
            })
            .Build();
        HorizonArtifactRequestService requests = new(new HorizonCapabilityService(configuration));

        HorizonArtifactRequestReceipt receipt = requests.BuildRequest(
            new HorizonArtifactRequestCreateRequest(
                HorizonId: "jackpoint",
                ArtifactKindOrCapabilityId: "briefing_video",
                UserId: "subject.dispatch",
                SourceRef: "jackpoint:emerald-sprawl-briefing",
                Visibility: "public_safe",
                ExternalProcessingConsent: true),
            new DateTimeOffset(2026, 6, 26, 10, 0, 0, TimeSpan.Zero));

        Assert.Equal("accepted", receipt.Status);
        Assert.Equal("jackpoint-briefing-video", receipt.CapabilityId);
        Assert.Empty(receipt.BlockedReasons);
        Assert.StartsWith("horizon-artifact-", receipt.RequestId, StringComparison.Ordinal);
    }

    [Fact]
    public void HorizonArtifactRequestModelBlocksCrossHorizonSourceRef()
    {
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_HORIZON_JACKPOINT_CAPABILITY_JACKPOINT_BRIEFING_VIDEO_ENABLED"] = "true"
            })
            .Build();
        HorizonArtifactRequestService requests = new(new HorizonCapabilityService(configuration));

        HorizonArtifactRequestReceipt receipt = requests.BuildRequest(
            new HorizonArtifactRequestCreateRequest(
                HorizonId: "jackpoint",
                ArtifactKindOrCapabilityId: "briefing_video",
                UserId: "subject.dispatch",
                SourceRef: "runbook-press:wrong-horizon-source",
                Visibility: "public_safe",
                ExternalProcessingConsent: true),
            new DateTimeOffset(2026, 6, 26, 10, 0, 0, TimeSpan.Zero));

        Assert.Equal("blocked", receipt.Status);
        Assert.Contains("horizon source reference", receipt.BlockedReasons);
    }

    [Fact]
    public void HorizonArtifactRequestModelCanConsumeGenericRunbookQuota()
    {
        using Fixture fixture = new(configureSettings: settings =>
        {
            settings["CHUMMER_HORIZON_RUNBOOK_PRESS_CAPABILITY_RUNBOOK_EXPORT_ENABLED"] = "true";
            settings["CHUMMER_HORIZON_RUNBOOK_PRESS_CAPABILITY_RUNBOOK_EXPORT_FREE_WEEKLY_LIMIT"] = "1";
        });
        HorizonCapabilityService capabilities = new(fixture.Configuration);
        HorizonArtifactQuotaService quota = new(
            new HorizonArtifactUsageStore(fixture.Configuration),
            capabilities,
            fixture.Billing);
        HorizonArtifactRequestService requests = new(capabilities, quota);
        DateTimeOffset now = new(2026, 6, 26, 10, 0, 0, TimeSpan.Zero);

        HorizonArtifactRequestReceipt accepted = requests.BuildRequest(
            new HorizonArtifactRequestCreateRequest(
                HorizonId: "runbook-press",
                ArtifactKindOrCapabilityId: "document_export",
                UserId: "subject.runbook",
                SourceRef: "runbook-press:new-runner-primer",
                Visibility: "public_safe",
                ExternalProcessingConsent: true,
                Email: "runbook@example.test"),
            now,
            consumeQuota: true);

        HorizonArtifactRequestReceipt exhausted = requests.BuildRequest(
            new HorizonArtifactRequestCreateRequest(
                HorizonId: "runbook-press",
                ArtifactKindOrCapabilityId: "document_export",
                UserId: "subject.runbook",
                SourceRef: "runbook-press:gm-first-night-primer",
                Visibility: "public_safe",
                ExternalProcessingConsent: true,
                Email: "runbook@example.test"),
            now.AddMinutes(1),
            consumeQuota: true);

        Assert.Equal("accepted", accepted.Status);
        Assert.Equal("runbook-export", accepted.CapabilityId);
        Assert.NotNull(accepted.Quota);
        Assert.Equal(1, accepted.Quota!.WeeklyLimit);
        Assert.Equal(1, accepted.Quota.WeeklyUsed);
        Assert.Equal(0, accepted.Quota.WeeklyRemaining);
        Assert.Equal("blocked", exhausted.Status);
        Assert.Contains("artifact allowance", exhausted.BlockedReasons);
        Assert.Null(exhausted.Quota);
    }

    [Fact]
    public void HorizonArtifactRequestModelDoesNotConsumeQuotaForCrossHorizonSourceRef()
    {
        using Fixture fixture = new(configureSettings: settings =>
        {
            settings["CHUMMER_HORIZON_RUNBOOK_PRESS_CAPABILITY_RUNBOOK_EXPORT_ENABLED"] = "true";
            settings["CHUMMER_HORIZON_RUNBOOK_PRESS_CAPABILITY_RUNBOOK_EXPORT_FREE_WEEKLY_LIMIT"] = "1";
        });
        HorizonCapabilityService capabilities = new(fixture.Configuration);
        HorizonArtifactQuotaService quota = new(
            new HorizonArtifactUsageStore(fixture.Configuration),
            capabilities,
            fixture.Billing);
        HorizonArtifactRequestService requests = new(capabilities, quota);
        DateTimeOffset now = new(2026, 6, 26, 10, 0, 0, TimeSpan.Zero);

        HorizonArtifactRequestReceipt blocked = requests.BuildRequest(
            new HorizonArtifactRequestCreateRequest(
                HorizonId: "runbook-press",
                ArtifactKindOrCapabilityId: "document_export",
                UserId: "subject.runbook-source-ref",
                SourceRef: "jackpoint:wrong-horizon-source",
                Visibility: "public_safe",
                ExternalProcessingConsent: true),
            now,
            consumeQuota: true);
        HorizonArtifactRequestReceipt accepted = requests.BuildRequest(
            new HorizonArtifactRequestCreateRequest(
                HorizonId: "runbook-press",
                ArtifactKindOrCapabilityId: "document_export",
                UserId: "subject.runbook-source-ref",
                SourceRef: "runbook-press:correct-horizon-source",
                Visibility: "public_safe",
                ExternalProcessingConsent: true),
            now.AddMinutes(1),
            consumeQuota: true);

        Assert.Equal("blocked", blocked.Status);
        Assert.Contains("horizon source reference", blocked.BlockedReasons);
        Assert.Null(blocked.Quota);
        Assert.Equal("accepted", accepted.Status);
        Assert.Equal(1, accepted.Quota?.WeeklyUsed);
        Assert.Equal("free", accepted.Quota?.AllowanceTier);
        Assert.Equal("free_weekly_allowance", accepted.Quota?.EntitlementBasis);
        Assert.Equal("account", accepted.Quota?.EntitlementScope);
    }

    [Fact]
    public void HorizonArtifactRequestReceiptsPersistAcrossStoreReloads()
    {
        using Fixture fixture = new(configureSettings: settings =>
        {
            settings["CHUMMER_HORIZON_RUNBOOK_PRESS_CAPABILITY_RUNBOOK_EXPORT_ENABLED"] = "true";
            settings["CHUMMER_HORIZON_RUNBOOK_PRESS_CAPABILITY_RUNBOOK_EXPORT_FREE_WEEKLY_LIMIT"] = "1";
        });
        HorizonCapabilityService capabilities = new(fixture.Configuration);
        HorizonArtifactQuotaService quota = new(
            new HorizonArtifactUsageStore(fixture.Configuration),
            capabilities,
            fixture.Billing);
        HorizonArtifactRequestReceiptStore store = new(fixture.Configuration);
        HorizonArtifactRequestService requests = new(capabilities, quota, store);
        DateTimeOffset now = new(2026, 6, 26, 10, 0, 0, TimeSpan.Zero);

        HorizonArtifactRequestReceipt accepted = requests.BuildRequest(
            new HorizonArtifactRequestCreateRequest(
                HorizonId: "runbook-press",
                ArtifactKindOrCapabilityId: "document_export",
                UserId: "subject.receipts",
                SourceRef: "runbook-press:persistent-primer",
                Visibility: "public_safe",
                ExternalProcessingConsent: true),
            now,
            consumeQuota: true);
        HorizonArtifactRequestReceipt blocked = requests.BuildRequest(
            new HorizonArtifactRequestCreateRequest(
                HorizonId: "jackpoint",
                ArtifactKindOrCapabilityId: "briefing_video",
                UserId: "subject.receipts",
                SourceRef: "jackpoint:blocked-briefing",
                Visibility: "public_safe",
                ExternalProcessingConsent: false),
            now.AddMinutes(1),
            consumeQuota: true);

        HorizonArtifactRequestReceiptStore reloaded = new(fixture.Configuration);
        IReadOnlyList<HorizonArtifactRequestReceipt> recent = reloaded.ListRecent(userId: "subject.receipts", limit: 10);

        Assert.Equal(2, recent.Count);
        Assert.Contains(recent, receipt => receipt.RequestId == accepted.RequestId && receipt.Status == "accepted");
        Assert.Contains(recent, receipt => receipt.RequestId == blocked.RequestId && receipt.Status == "blocked");
        Assert.All(recent, receipt =>
        {
            string serialized = JsonSerializer.Serialize(receipt);
            Assert.DoesNotContain("MarkupGo", serialized, StringComparison.OrdinalIgnoreCase);
            Assert.DoesNotContain("vidBoard", serialized, StringComparison.OrdinalIgnoreCase);
            Assert.DoesNotContain("BrilliantDirectories", serialized, StringComparison.OrdinalIgnoreCase);
            Assert.DoesNotContain("Brilliant Directories", serialized, StringComparison.OrdinalIgnoreCase);
        });
        HorizonArtifactRequestReceipt acceptedReceipt = Assert.Single(recent, receipt => receipt.RequestId == accepted.RequestId);
        Assert.Equal("free", acceptedReceipt.Quota?.AllowanceTier);
        Assert.Equal("free_weekly_allowance", acceptedReceipt.Quota?.EntitlementBasis);
        Assert.Equal("account", acceptedReceipt.Quota?.EntitlementScope);
    }

    [Fact]
    public void InternalHorizonCapabilitiesEndpointRequiresTokenAndCanReturnPublicSafeHealth()
    {
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["FLEET_INTERNAL_API_TOKEN"] = "test-internal-token"
            })
            .Build();
        HorizonCapabilityService capabilities = new(configuration);
        var controller = new InternalHorizonCapabilitiesController(
            capabilities,
            new HorizonArtifactQuotaService(new HorizonArtifactUsageStore(configuration), capabilities, new BrilliantDirectoriesBillingService(new BrilliantDirectoriesBillingStore(configuration), new MyFirstBookUsageStore(configuration), configuration)),
            new HorizonArtifactRequestService(capabilities),
            configuration)
        {
            ControllerContext = new ControllerContext
            {
                HttpContext = new DefaultHttpContext()
            }
        };

        ActionResult<HorizonCapabilityHealthCatalog> denied = controller.ListCapabilities(publicSafe: true);
        ObjectResult deniedProblem = Assert.IsType<ObjectResult>(denied.Result);
        Assert.Equal(StatusCodes.Status401Unauthorized, deniedProblem.StatusCode);

        controller.ControllerContext.HttpContext.Request.Headers.Authorization = "Bearer test-internal-token";
        ActionResult<HorizonCapabilityHealthCatalog> result = controller.ListCapabilities(publicSafe: true);
        OkObjectResult ok = Assert.IsType<OkObjectResult>(result.Result);
        HorizonCapabilityHealthCatalog catalog = Assert.IsType<HorizonCapabilityHealthCatalog>(ok.Value);
        HorizonCapabilityHealthSnapshot runsiteTour = Assert.Single(catalog.Capabilities, item => item.CapabilityId == "runsite-tour");
        Assert.True(catalog.PublicSafe);
        Assert.Null(runsiteTour.InternalProviderLane);
        Assert.Equal("available", runsiteTour.Status);
        Assert.Equal(1, runsiteTour.FreeWeeklyLimit);
        Assert.Equal(10, runsiteTour.SupporterWeeklyLimit);
        Assert.True(runsiteTour.QuotaTracked);
    }

    [Fact]
    public void PublicHorizonCapabilitiesEndpointReturnsOnlyPublicSafeVisibleHealth()
    {
        using Fixture fixture = new();
        PublicHorizonCapabilitiesController controller = new(new HorizonCapabilityService(fixture.Configuration));

        ActionResult<HorizonCapabilityHealthCatalog> result = controller.ListCapabilities();

        OkObjectResult ok = Assert.IsType<OkObjectResult>(result.Result);
        HorizonCapabilityHealthCatalog catalog = Assert.IsType<HorizonCapabilityHealthCatalog>(ok.Value);
        Assert.True(catalog.PublicSafe);
        Assert.All(catalog.Capabilities, capability =>
        {
            Assert.True(capability.PublicVisible);
            Assert.Null(capability.InternalProviderLane);
        });
        Assert.Contains(catalog.Capabilities, capability =>
            capability.HorizonId == "runsite"
            && capability.CapabilityId == "runsite-tour"
            && capability.Status == "available");
        Assert.Contains(catalog.Capabilities, capability =>
            capability.HorizonId == "runsite"
            && capability.CapabilityId == "runsite-map"
            && capability.Status == "disabled");

        string serialized = JsonSerializer.Serialize(catalog);
        Assert.DoesNotContain("Matterport", serialized, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("3DVista", serialized, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("AvoMap", serialized, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("MarkupGo", serialized, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("vidBoard", serialized, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void PublicHorizonCapabilitiesEndpointSupportsCapabilityScopedFilters()
    {
        using Fixture fixture = new();
        PublicHorizonCapabilitiesController controller = new(new HorizonCapabilityService(fixture.Configuration));

        ActionResult<HorizonCapabilityHealthCatalog> result = controller.ListCapabilities(
            horizonId: "runsite",
            artifactKindOrCapabilityId: "tour");

        OkObjectResult ok = Assert.IsType<OkObjectResult>(result.Result);
        HorizonCapabilityHealthCatalog catalog = Assert.IsType<HorizonCapabilityHealthCatalog>(ok.Value);
        HorizonCapabilityHealthSnapshot capability = Assert.Single(catalog.Capabilities);
        Assert.Equal("runsite", capability.HorizonId);
        Assert.Equal("runsite-tour", capability.CapabilityId);
        Assert.True(capability.PublicVisible);
        Assert.Null(capability.InternalProviderLane);
    }

    [Fact]
    public async Task HorizonCapabilityMeEndpointRequiresAuthentication()
    {
        using Fixture fixture = new(authenticated: false);
        var controller = new HorizonCapabilitiesController(
            new HorizonCapabilityService(fixture.Configuration),
            fixture.Identity,
            NullLogger<HorizonCapabilitiesController>.Instance)
        {
            ControllerContext = new ControllerContext
            {
                HttpContext = new DefaultHttpContext()
            }
        };

        ActionResult<HorizonCapabilityHealthCatalog> result = await controller.MyCapabilities(cancellationToken: CancellationToken.None);

        ObjectResult problem = Assert.IsType<ObjectResult>(result.Result);
        Assert.Equal(StatusCodes.Status401Unauthorized, problem.StatusCode);
    }

    [Fact]
    public async Task HorizonCapabilityMeEndpointReturnsSignedInPublicSafeCrossHorizonCatalog()
    {
        using Fixture fixture = new(configureSettings: settings =>
        {
            settings["CHUMMER_HORIZON_RUNBOOK_PRESS_CAPABILITY_RUNBOOK_EXPORT_ENABLED"] = "true";
            settings["CHUMMER_HORIZON_JACKPOINT_CAPABILITY_JACKPOINT_BRIEFING_VIDEO_ENABLED"] = "true";
        }, authenticated: true);
        var controller = new HorizonCapabilitiesController(
            new HorizonCapabilityService(fixture.Configuration),
            fixture.Identity,
            NullLogger<HorizonCapabilitiesController>.Instance)
        {
            ControllerContext = new ControllerContext
            {
                HttpContext = new DefaultHttpContext()
            }
        };
        controller.ControllerContext.HttpContext.Request.Headers.Authorization = "Bearer desktop-access-token";

        ActionResult<HorizonCapabilityHealthCatalog> result = await controller.MyCapabilities(
            cancellationToken: CancellationToken.None);

        OkObjectResult ok = Assert.IsType<OkObjectResult>(result.Result);
        HorizonCapabilityHealthCatalog catalog = Assert.IsType<HorizonCapabilityHealthCatalog>(ok.Value);
        Assert.True(catalog.PublicSafe);
        Assert.Contains(catalog.Capabilities, capability =>
            capability.HorizonId == "runbook-press"
            && capability.CapabilityId == "runbook-export"
            && capability.Status == "available");
        Assert.Contains(catalog.Capabilities, capability =>
            capability.HorizonId == "jackpoint"
            && capability.CapabilityId == "jackpoint-briefing-video"
            && capability.Status == "available");
        Assert.Contains(catalog.Capabilities, capability =>
            capability.HorizonId == "origin-dossier"
            && capability.CapabilityId == "origin-dossier-media"
            && capability.Status == "disabled");
        Assert.Contains(catalog.Capabilities, capability =>
            capability.HorizonId == "runner_passport"
            && capability.CapabilityId == "runner_passport-identity-network"
            && !capability.QuotaTracked);
        Assert.Contains(catalog.Capabilities, capability =>
            capability.HorizonId == "table-pulse"
            && capability.CapabilityId == "table-pulse-debrief");
        Assert.All(catalog.Capabilities, capability => Assert.Null(capability.InternalProviderLane));

        string serialized = JsonSerializer.Serialize(catalog);
        Assert.DoesNotContain("Matterport", serialized, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("3DVista", serialized, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("MarkupGo", serialized, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("vidBoard", serialized, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("Icanpreneur", serialized, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void HorizonCapabilityHealthExposesConfiguredQuotaLimitsWithoutProviderLane()
    {
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_HORIZON_RUNBOOK_PRESS_CAPABILITY_RUNBOOK_EXPORT_ENABLED"] = "true",
                ["CHUMMER_HORIZON_RUNBOOK_PRESS_CAPABILITY_RUNBOOK_EXPORT_FREE_WEEKLY_LIMIT"] = "3",
                ["CHUMMER_HORIZON_RUNBOOK_PRESS_CAPABILITY_RUNBOOK_EXPORT_SUPPORTER_WEEKLY_LIMIT"] = "12"
            })
            .Build();
        HorizonCapabilityService capabilities = new(configuration);

        HorizonCapabilityHealthSnapshot health = capabilities.GetHealth("runbook-press", "document_export", publicSafe: true);

        Assert.Equal("available", health.Status);
        Assert.Null(health.InternalProviderLane);
        Assert.Equal(3, health.FreeWeeklyLimit);
        Assert.Equal(12, health.SupporterWeeklyLimit);
        Assert.True(health.QuotaTracked);
        Assert.DoesNotContain("MarkupGo", JsonSerializer.Serialize(health), StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("Documentation.AI", JsonSerializer.Serialize(health), StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void InternalCapabilityLanesTrackCurrentOriginAndRunbookProviderBoundary()
    {
        using Fixture fixture = new();
        HorizonCapabilityService capabilities = new(fixture.Configuration);

        HorizonCapabilityHealthSnapshot runbook = capabilities.GetHealth("runbook-press", "document_export", publicSafe: false);
        HorizonCapabilityHealthSnapshot origin = capabilities.GetHealth("origin-dossier", "dossier_media", publicSafe: false);
        HorizonCapabilityHealthSnapshot publicSafeRunbook = capabilities.GetHealth("runbook-press", "document_export", publicSafe: true);
        HorizonCapabilityHealthSnapshot publicSafeOrigin = capabilities.GetHealth("origin-dossier", "dossier_media", publicSafe: true);

        Assert.Contains("Subscribr.ai", runbook.InternalProviderLane, StringComparison.Ordinal);
        Assert.Contains("First Book ai", runbook.InternalProviderLane, StringComparison.Ordinal);
        Assert.Contains("Subscribr.ai", origin.InternalProviderLane, StringComparison.Ordinal);
        Assert.Contains("First Book ai", origin.InternalProviderLane, StringComparison.Ordinal);
        Assert.Null(publicSafeRunbook.InternalProviderLane);
        Assert.Null(publicSafeOrigin.InternalProviderLane);
    }

    [Fact]
    public void InternalHorizonArtifactRequestEndpointConsumesGenericQuota()
    {
        using Fixture fixture = new(configureSettings: settings =>
        {
            settings["FLEET_INTERNAL_API_TOKEN"] = "test-internal-token";
            settings["CHUMMER_HORIZON_RUNBOOK_PRESS_CAPABILITY_RUNBOOK_EXPORT_ENABLED"] = "true";
            settings["CHUMMER_HORIZON_RUNBOOK_PRESS_CAPABILITY_RUNBOOK_EXPORT_FREE_WEEKLY_LIMIT"] = "1";
        });
        HorizonCapabilityService capabilities = new(fixture.Configuration);
        HorizonArtifactQuotaService quota = new(
            new HorizonArtifactUsageStore(fixture.Configuration),
            capabilities,
            fixture.Billing);
        var controller = new InternalHorizonCapabilitiesController(
            capabilities,
            quota,
            new HorizonArtifactRequestService(capabilities, quota),
            fixture.Configuration)
        {
            ControllerContext = new ControllerContext
            {
                HttpContext = new DefaultHttpContext()
            }
        };
        controller.ControllerContext.HttpContext.Request.Headers.Authorization = "Bearer test-internal-token";

        ActionResult<HorizonArtifactRequestReceipt> accepted = controller.BuildArtifactRequest(
            new HorizonArtifactRequestCreateRequest(
                HorizonId: "runbook-press",
                ArtifactKindOrCapabilityId: "document_export",
                UserId: "subject.internal-runbook",
                SourceRef: "runbook-press:new-runner-primer",
                Visibility: "public_safe",
                ExternalProcessingConsent: true));
        ActionResult<HorizonArtifactRequestReceipt> exhausted = controller.BuildArtifactRequest(
            new HorizonArtifactRequestCreateRequest(
                HorizonId: "runbook-press",
                ArtifactKindOrCapabilityId: "document_export",
                UserId: "subject.internal-runbook",
                SourceRef: "runbook-press:gm-first-night-primer",
                Visibility: "public_safe",
                ExternalProcessingConsent: true));

        HorizonArtifactRequestReceipt acceptedReceipt = Assert.IsType<HorizonArtifactRequestReceipt>(Assert.IsType<OkObjectResult>(accepted.Result).Value);
        HorizonArtifactRequestReceipt exhaustedReceipt = Assert.IsType<HorizonArtifactRequestReceipt>(Assert.IsType<OkObjectResult>(exhausted.Result).Value);
        Assert.Equal("accepted", acceptedReceipt.Status);
        Assert.True(acceptedReceipt.QuotaTracked);
        Assert.Equal(0, acceptedReceipt.Quota?.WeeklyRemaining);
        Assert.Equal("blocked", exhaustedReceipt.Status);
        Assert.Contains("artifact allowance", exhaustedReceipt.BlockedReasons);
    }

    [Fact]
    public void InternalHorizonArtifactRequestEndpointAcceptsNonQuotaTrackedCapability()
    {
        using Fixture fixture = new(configureSettings: settings =>
        {
            settings["FLEET_INTERNAL_API_TOKEN"] = "test-internal-token";
        });
        HorizonCapabilityService capabilities = new(fixture.Configuration);
        HorizonArtifactQuotaService quota = new(
            new HorizonArtifactUsageStore(fixture.Configuration),
            capabilities,
            fixture.Billing);
        var controller = new InternalHorizonCapabilitiesController(
            capabilities,
            quota,
            new HorizonArtifactRequestService(capabilities, quota),
            fixture.Configuration)
        {
            ControllerContext = new ControllerContext
            {
                HttpContext = new DefaultHttpContext()
            }
        };
        controller.ControllerContext.HttpContext.Request.Headers.Authorization = "Bearer test-internal-token";

        ActionResult<HorizonArtifactRequestReceipt> result = controller.BuildArtifactRequest(
            new HorizonArtifactRequestCreateRequest(
                HorizonId: "runner_passport",
                ArtifactKindOrCapabilityId: "identity_network",
                UserId: "subject.internal-passport",
                SourceRef: "runner_passport:identity-network",
                Visibility: "public_safe",
                ExternalProcessingConsent: true));

        HorizonArtifactRequestReceipt receipt = Assert.IsType<HorizonArtifactRequestReceipt>(Assert.IsType<OkObjectResult>(result.Result).Value);
        Assert.Equal("accepted", receipt.Status);
        Assert.False(receipt.QuotaTracked);
        Assert.Null(receipt.Quota);
        Assert.Empty(receipt.BlockedReasons);
    }

    [Fact]
    public void InternalHorizonArtifactRequestEndpointListsPersistedReceipts()
    {
        using Fixture fixture = new(configureSettings: settings =>
        {
            settings["FLEET_INTERNAL_API_TOKEN"] = "test-internal-token";
            settings["CHUMMER_HORIZON_RUNBOOK_PRESS_CAPABILITY_RUNBOOK_EXPORT_ENABLED"] = "true";
            settings["CHUMMER_HORIZON_RUNBOOK_PRESS_CAPABILITY_RUNBOOK_EXPORT_FREE_WEEKLY_LIMIT"] = "2";
        });
        HorizonCapabilityService capabilities = new(fixture.Configuration);
        HorizonArtifactQuotaService quota = new(
            new HorizonArtifactUsageStore(fixture.Configuration),
            capabilities,
            fixture.Billing);
        HorizonArtifactRequestReceiptStore store = new(fixture.Configuration);
        var controller = new InternalHorizonCapabilitiesController(
            capabilities,
            quota,
            new HorizonArtifactRequestService(capabilities, quota, store),
            fixture.Configuration)
        {
            ControllerContext = new ControllerContext
            {
                HttpContext = new DefaultHttpContext()
            }
        };
        controller.ControllerContext.HttpContext.Request.Headers.Authorization = "Bearer test-internal-token";
        _ = controller.BuildArtifactRequest(
            new HorizonArtifactRequestCreateRequest(
                HorizonId: "runbook-press",
                ArtifactKindOrCapabilityId: "document_export",
                UserId: "subject.internal-receipts",
                SourceRef: "runbook-press:persistent-internal-primer",
                Visibility: "public_safe",
                ExternalProcessingConsent: true));

        ActionResult<HorizonArtifactRequestReceiptCatalog> result = controller.ListArtifactRequests(
            horizonId: "runbook-press",
            userId: "subject.internal-receipts",
            limit: 5);

        OkObjectResult ok = Assert.IsType<OkObjectResult>(result.Result);
        HorizonArtifactRequestReceiptCatalog catalog = Assert.IsType<HorizonArtifactRequestReceiptCatalog>(ok.Value);
        HorizonArtifactRequestReceipt receipt = Assert.Single(catalog.Receipts);
        Assert.Equal("runbook-press", catalog.HorizonId);
        Assert.Equal("subject.internal-receipts", catalog.UserId);
        Assert.Equal("accepted", receipt.Status);
        Assert.Equal("runbook-press:persistent-internal-primer", receipt.SourceRef);
        Assert.DoesNotContain("MarkupGo", JsonSerializer.Serialize(catalog), StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("Documentation.AI", JsonSerializer.Serialize(catalog), StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void InternalHorizonQuotaEndpointListsPublicVisibleCrossHorizonAllowanceCatalog()
    {
        using Fixture fixture = new(configureSettings: settings =>
        {
            settings["FLEET_INTERNAL_API_TOKEN"] = "test-internal-token";
            settings["CHUMMER_HORIZON_RUNBOOK_PRESS_CAPABILITY_RUNBOOK_EXPORT_ENABLED"] = "true";
            settings["CHUMMER_HORIZON_RUNBOOK_PRESS_CAPABILITY_RUNBOOK_EXPORT_FREE_WEEKLY_LIMIT"] = "2";
        });
        HorizonCapabilityService capabilities = new(fixture.Configuration);
        HorizonArtifactQuotaService quota = new(
            new HorizonArtifactUsageStore(fixture.Configuration),
            capabilities,
            fixture.Billing);
        var controller = new InternalHorizonCapabilitiesController(
            capabilities,
            quota,
            new HorizonArtifactRequestService(capabilities, quota),
            fixture.Configuration)
        {
            ControllerContext = new ControllerContext
            {
                HttpContext = new DefaultHttpContext()
            }
        };
        controller.ControllerContext.HttpContext.Request.Headers.Authorization = "Bearer test-internal-token";

        ActionResult<HorizonArtifactQuotaCatalog> result = controller.ListQuotas(
            userId: "subject.internal-quotas",
            email: "internal@example.com",
            publicVisibleOnly: true);

        OkObjectResult ok = Assert.IsType<OkObjectResult>(result.Result);
        HorizonArtifactQuotaCatalog catalog = Assert.IsType<HorizonArtifactQuotaCatalog>(ok.Value);
        Assert.Equal("subject.internal-quotas", catalog.UserId);
        Assert.True(catalog.PublicVisibleOnly);
        Assert.Equal(3, catalog.Quotas.Count);
        Assert.Contains(catalog.Quotas, quota => quota.CapabilityId == "runsite-tour");
        Assert.Contains(catalog.Quotas, quota => quota.CapabilityId == "runsite-map");
        Assert.Contains(catalog.Quotas, quota => quota.CapabilityId == "propertyquarry-tour");
        Assert.DoesNotContain(catalog.Quotas, quota => quota.CapabilityId == "runbook-export");
        Assert.All(catalog.Quotas, quota =>
        {
            Assert.Equal("free", quota.AllowanceTier);
            Assert.Equal("free_weekly_allowance", quota.EntitlementBasis);
            Assert.Equal("account", quota.EntitlementScope);
        });

        string serialized = JsonSerializer.Serialize(catalog);
        Assert.DoesNotContain("Matterport", serialized, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("3DVista", serialized, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("BrilliantDirectories", serialized, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task HorizonArtifactQuotaMeEndpointRequiresAuthentication()
    {
        using Fixture fixture = new(authenticated: false);
        var controller = new HorizonArtifactQuotasController(
            fixture.HorizonArtifactQuota,
            fixture.Identity,
            NullLogger<HorizonArtifactQuotasController>.Instance)
        {
            ControllerContext = new ControllerContext
            {
                HttpContext = new DefaultHttpContext()
            }
        };

        ActionResult<HorizonArtifactQuotaCatalog> result = await controller.MyQuotas(cancellationToken: CancellationToken.None);

        ObjectResult problem = Assert.IsType<ObjectResult>(result.Result);
        Assert.Equal(StatusCodes.Status401Unauthorized, problem.StatusCode);
    }

    [Fact]
    public async Task HorizonArtifactQuotaMeEndpointReturnsSignedInCrossHorizonCatalog()
    {
        using Fixture fixture = new(authenticated: true);
        fixture.Billing.SyncMember(
            new Chummer.Run.Contracts.Billing.BrilliantDirectoriesMemberSyncRequest(
                UserId: "subject.dispatch",
                MemberId: "supporter-membership",
                Email: "dispatch@example.com",
                PlanKey: "supporter",
                PlanName: "Supporter",
                MembershipStatus: "active",
                SupporterActive: true,
                ObservedAtUtc: new DateTimeOffset(2026, 6, 24, 10, 0, 0, TimeSpan.Zero)),
            "sync-secret");
        var controller = new HorizonArtifactQuotasController(
            fixture.HorizonArtifactQuota,
            fixture.Identity,
            NullLogger<HorizonArtifactQuotasController>.Instance)
        {
            ControllerContext = new ControllerContext
            {
                HttpContext = new DefaultHttpContext()
            }
        };
        controller.ControllerContext.HttpContext.Request.Headers.Authorization = "Bearer desktop-access-token";

        ActionResult<HorizonArtifactQuotaCatalog> result = await controller.MyQuotas(
            horizonId: "runsite",
            publicVisibleOnly: true,
            cancellationToken: CancellationToken.None);

        OkObjectResult ok = Assert.IsType<OkObjectResult>(result.Result);
        HorizonArtifactQuotaCatalog catalog = Assert.IsType<HorizonArtifactQuotaCatalog>(ok.Value);
        Assert.Equal("subject.dispatch", catalog.UserId);
        Assert.Equal("runsite", catalog.HorizonId);
        Assert.True(catalog.PublicVisibleOnly);
        Assert.Equal(2, catalog.Quotas.Count);
        Assert.All(catalog.Quotas, quota => Assert.Equal("runsite", quota.HorizonId));
        Assert.Contains(catalog.Quotas, quota =>
            quota.CapabilityId == "runsite-tour"
            && quota.AllowanceTier == "supporter"
            && quota.EntitlementBasis == "supporter_weekly_allowance"
            && quota.EntitlementScope == "account"
            && quota.WeeklyLimit == 10);
        Assert.Contains(catalog.Quotas, quota =>
            quota.CapabilityId == "runsite-map"
            && quota.AllowanceTier == "supporter"
            && quota.WeeklyLimit == 10);

        string serialized = JsonSerializer.Serialize(catalog);
        Assert.DoesNotContain("Matterport", serialized, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("3DVista", serialized, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("BrilliantDirectories", serialized, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("Brilliant Directories", serialized, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task HorizonArtifactRequestMeEndpointRequiresAuthentication()
    {
        using Fixture fixture = new(authenticated: false);
        var controller = new HorizonArtifactRequestsController(
            new HorizonArtifactRequestService(new HorizonCapabilityService(fixture.Configuration), fixture.HorizonArtifactQuota, fixture.ArtifactRequestReceipts),
            fixture.Identity,
            NullLogger<HorizonArtifactRequestsController>.Instance)
        {
            ControllerContext = new ControllerContext
            {
                HttpContext = new DefaultHttpContext()
            }
        };

        ActionResult<HorizonArtifactRequestReceiptCatalog> result = await controller.MyArtifactRequests(cancellationToken: CancellationToken.None);

        ObjectResult problem = Assert.IsType<ObjectResult>(result.Result);
        Assert.Equal(StatusCodes.Status401Unauthorized, problem.StatusCode);
    }

    [Fact]
    public async Task HorizonArtifactRequestMeReceiptEndpointReturnsOwnedReceipt()
    {
        using Fixture fixture = new(authenticated: true);
        HorizonCapabilityService capabilities = new(fixture.Configuration);
        HorizonArtifactRequestService requests = new(capabilities, fixture.HorizonArtifactQuota, fixture.ArtifactRequestReceipts);
        HorizonArtifactRequestReceipt receipt = requests.BuildRequest(
            new HorizonArtifactRequestCreateRequest(
                HorizonId: "runsite",
                ArtifactKindOrCapabilityId: "tour",
                UserId: "subject.dispatch",
                SourceRef: "runsite:redmond-dockyard-pack",
                Visibility: "private",
                ExternalProcessingConsent: true,
                Email: "dispatch@example.com"),
            new DateTimeOffset(2026, 6, 26, 12, 0, 0, TimeSpan.Zero),
            consumeQuota: true);

        var controller = new HorizonArtifactRequestsController(
            requests,
            fixture.Identity,
            NullLogger<HorizonArtifactRequestsController>.Instance)
        {
            ControllerContext = new ControllerContext
            {
                HttpContext = new DefaultHttpContext()
            }
        };
        controller.ControllerContext.HttpContext.Request.Headers.Authorization = "Bearer desktop-access-token";

        ActionResult<HorizonArtifactRequestReceipt> result = await controller.MyArtifactRequest(
            receipt.RequestId,
            CancellationToken.None);

        OkObjectResult ok = Assert.IsType<OkObjectResult>(result.Result);
        HorizonArtifactRequestReceipt payload = Assert.IsType<HorizonArtifactRequestReceipt>(ok.Value);
        Assert.Equal(receipt.RequestId, payload.RequestId);
        Assert.Equal("runsite:redmond-dockyard-pack", payload.SourceRef);
        Assert.Equal("private", payload.Visibility);
        Assert.Equal("subject.dispatch", payload.RequestedByUserId);
    }

    [Fact]
    public void PublicHorizonArtifactRequestEndpointReturnsRedactedPublicSafeReceipt()
    {
        using Fixture fixture = new();
        HorizonCapabilityService capabilities = new(fixture.Configuration);
        HorizonArtifactRequestService requests = new(capabilities, fixture.HorizonArtifactQuota, fixture.ArtifactRequestReceipts);
        HorizonArtifactRequestReceipt receipt = requests.BuildRequest(
            new HorizonArtifactRequestCreateRequest(
                HorizonId: "black-ledger",
                ArtifactKindOrCapabilityId: "newsroom_bulletin",
                UserId: "subject.public-viewer",
                SourceRef: "black-ledger:turn-1:newsroom",
                Visibility: "public_safe",
                ExternalProcessingConsent: true,
                Email: "viewer@example.com"),
            new DateTimeOffset(2026, 6, 26, 12, 0, 0, TimeSpan.Zero),
            consumeQuota: false,
            requireRequestingUser: false);

        var controller = new HorizonArtifactRequestsController(
            requests,
            fixture.Identity,
            NullLogger<HorizonArtifactRequestsController>.Instance);

        ActionResult<PublicHorizonArtifactRequestReceipt> result = controller.PublicArtifactRequest(receipt.RequestId);

        OkObjectResult ok = Assert.IsType<OkObjectResult>(result.Result);
        PublicHorizonArtifactRequestReceipt payload = Assert.IsType<PublicHorizonArtifactRequestReceipt>(ok.Value);
        Assert.Equal(receipt.RequestId, payload.RequestId);
        Assert.Equal("black-ledger", payload.HorizonId);
        Assert.Equal("black-ledger-newsroom", payload.CapabilityId);
        Assert.Equal("public_safe", payload.Visibility);
        Assert.True(payload.PublicSafe);
        Assert.False(payload.QuotaTracked);
        Assert.Equal("/api/v1/public/horizons/capabilities?horizonId=black-ledger&artifactKindOrCapabilityId=black-ledger-newsroom", payload.CapabilityHealthHref);
        Assert.Equal($"/api/v1/public/horizons/artifact-requests/{receipt.RequestId}", payload.PublicReceiptHref);

        string serialized = JsonSerializer.Serialize(payload);
        Assert.DoesNotContain("subject.public-viewer", serialized, StringComparison.Ordinal);
        Assert.DoesNotContain("viewer@example.com", serialized, StringComparison.Ordinal);
    }

    [Fact]
    public void PublicHorizonArtifactRequestEndpointDoesNotExposePrivateReceipt()
    {
        using Fixture fixture = new();
        HorizonCapabilityService capabilities = new(fixture.Configuration);
        HorizonArtifactRequestService requests = new(capabilities, fixture.HorizonArtifactQuota, fixture.ArtifactRequestReceipts);
        HorizonArtifactRequestReceipt receipt = requests.BuildRequest(
            new HorizonArtifactRequestCreateRequest(
                HorizonId: "runsite",
                ArtifactKindOrCapabilityId: "tour",
                UserId: "subject.dispatch",
                SourceRef: "runsite:redmond-dockyard-pack",
                Visibility: "private",
                ExternalProcessingConsent: true,
                Email: "dispatch@example.com"),
            new DateTimeOffset(2026, 6, 26, 12, 0, 0, TimeSpan.Zero),
            consumeQuota: false);

        var controller = new HorizonArtifactRequestsController(
            requests,
            fixture.Identity,
            NullLogger<HorizonArtifactRequestsController>.Instance);

        ActionResult<PublicHorizonArtifactRequestReceipt> result = controller.PublicArtifactRequest(receipt.RequestId);

        Assert.IsType<NotFoundResult>(result.Result);
    }

    [Fact]
    public async Task HorizonArtifactRequestMeEndpointReturnsSignedInCrossHorizonReceipts()
    {
        using Fixture fixture = new(authenticated: true);
        HorizonCapabilityService capabilities = new(fixture.Configuration);
        HorizonArtifactRequestService requests = new(capabilities, fixture.HorizonArtifactQuota, fixture.ArtifactRequestReceipts);
        DateTimeOffset now = new(2026, 6, 26, 12, 0, 0, TimeSpan.Zero);

        _ = requests.BuildRequest(
            new HorizonArtifactRequestCreateRequest(
                HorizonId: "runsite",
                ArtifactKindOrCapabilityId: "tour",
                UserId: "subject.dispatch",
                SourceRef: "runsite:redmond-dockyard-pack",
                Visibility: "private",
                ExternalProcessingConsent: true,
                Email: "dispatch@example.com"),
            now,
            consumeQuota: true);
        _ = requests.BuildRequest(
            new HorizonArtifactRequestCreateRequest(
                HorizonId: "propertyquarry",
                ArtifactKindOrCapabilityId: "tour",
                UserId: "subject.dispatch",
                SourceRef: "propertyquarry:northbound-research-lab",
                Visibility: "private",
                ExternalProcessingConsent: true,
                Email: "dispatch@example.com"),
            now.AddMinutes(1),
            consumeQuota: true);
        _ = requests.BuildRequest(
            new HorizonArtifactRequestCreateRequest(
                HorizonId: "runsite",
                ArtifactKindOrCapabilityId: "tour",
                UserId: "subject.dispatch",
                SourceRef: "runsite:everett-switchyard-pack",
                Visibility: "private",
                ExternalProcessingConsent: true,
                Email: "dispatch@example.com"),
            now.AddMinutes(2),
            consumeQuota: true);

        var controller = new HorizonArtifactRequestsController(
            requests,
            fixture.Identity,
            NullLogger<HorizonArtifactRequestsController>.Instance)
        {
            ControllerContext = new ControllerContext
            {
                HttpContext = new DefaultHttpContext()
            }
        };
        controller.ControllerContext.HttpContext.Request.Headers.Authorization = "Bearer desktop-access-token";

        ActionResult<HorizonArtifactRequestReceiptCatalog> filteredResult = await controller.MyArtifactRequests(
            horizonId: "runsite",
            limit: 10,
            cancellationToken: CancellationToken.None);
        OkObjectResult filteredOk = Assert.IsType<OkObjectResult>(filteredResult.Result);
        HorizonArtifactRequestReceiptCatalog filteredCatalog = Assert.IsType<HorizonArtifactRequestReceiptCatalog>(filteredOk.Value);
        Assert.Equal("subject.dispatch", filteredCatalog.UserId);
        Assert.Equal("runsite", filteredCatalog.HorizonId);
        Assert.Equal(2, filteredCatalog.Receipts.Count);
        Assert.Equal("runsite:everett-switchyard-pack", filteredCatalog.Receipts[0].SourceRef);
        Assert.Equal("blocked", filteredCatalog.Receipts[0].Status);
        Assert.Equal("runsite:redmond-dockyard-pack", filteredCatalog.Receipts[1].SourceRef);
        Assert.Equal("accepted", filteredCatalog.Receipts[1].Status);

        ActionResult<HorizonArtifactRequestReceiptCatalog> allResult = await controller.MyArtifactRequests(
            limit: 10,
            cancellationToken: CancellationToken.None);
        OkObjectResult allOk = Assert.IsType<OkObjectResult>(allResult.Result);
        HorizonArtifactRequestReceiptCatalog allCatalog = Assert.IsType<HorizonArtifactRequestReceiptCatalog>(allOk.Value);
        Assert.Equal(3, allCatalog.Receipts.Count);
        Assert.Contains(allCatalog.Receipts, receipt => receipt.HorizonId == "propertyquarry" && receipt.SourceRef == "propertyquarry:northbound-research-lab");

        string serialized = JsonSerializer.Serialize(allCatalog);
        Assert.DoesNotContain("Matterport", serialized, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("3DVista", serialized, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("BrilliantDirectories", serialized, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("MarkupGo", serialized, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("vidBoard", serialized, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void HorizonArtifactDispatchNoLongerCarriesRunsiteOnlyQuotaFallback()
    {
        string controller = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "PublicLandingController.cs"));

        Assert.DoesNotContain("allowLegacyRunsiteQuotaFallback", controller, StringComparison.Ordinal);
        Assert.DoesNotContain("else if (allowLegacyRunsiteQuotaFallback)", controller, StringComparison.Ordinal);
        Assert.Contains("Shared horizon artifact dispatch service is not available right now.", controller, StringComparison.Ordinal);
    }

    [Fact]
    public async Task KarmaForgePageIncludesPublicSafeDiscoveryCapability()
    {
        using Fixture fixture = new(configureSettings: settings =>
        {
            settings["CHUMMER_HORIZON_KARMA_FORGE_CAPABILITY_KARMA_FORGE_DISCOVERY_ENABLED"] = "true";
        });
        fixture.Controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };
        fixture.Controller.ControllerContext.HttpContext.Request.Path = "/participate/karma-forge";

        IActionResult result = await fixture.Controller.KarmaForgePage(track: null, CancellationToken.None);

        ViewResult view = Assert.IsType<ViewResult>(result);
        KarmaForgeIntakePageViewModel model = Assert.IsType<KarmaForgeIntakePageViewModel>(view.Model);
        Assert.Equal("karma-forge", model.DiscoveryCapability.HorizonId);
        Assert.Equal("karma-forge-discovery", model.DiscoveryCapability.CapabilityId);
        Assert.Equal("discovery_packet", model.DiscoveryCapability.ArtifactKind);
        Assert.Equal("Discovery Packet", model.DiscoveryCapability.PublicLabel);
        Assert.Equal("demand_validation", model.DiscoveryCapability.CapabilitySlot);
        Assert.Equal("available", model.DiscoveryCapability.Status);
        Assert.True(model.DiscoveryCapability.RequestSupported);
        Assert.Equal("karma-forge:public-intake", model.DiscoveryCapability.SourceRef);
    }

    [Fact]
    public async Task KarmaForgeSubmittedPageIncludesPublicSafeDiscoveryCapabilitySourceRef()
    {
        using Fixture fixture = new();
        fixture.Controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };
        fixture.Controller.ControllerContext.HttpContext.Request.Path = "/participate/karma-forge/submitted/sample-submission-id";

        IActionResult result = await fixture.Controller.KarmaForgeSubmittedPage("sample-submission-id", CancellationToken.None);

        ViewResult view = Assert.IsType<ViewResult>(result);
        KarmaForgeSubmittedPageViewModel model = Assert.IsType<KarmaForgeSubmittedPageViewModel>(view.Model);
        Assert.Equal("karma-forge", model.DiscoveryCapability.HorizonId);
        Assert.Equal("karma-forge-discovery", model.DiscoveryCapability.CapabilityId);
        Assert.Equal("disabled", model.DiscoveryCapability.Status);
        Assert.False(model.DiscoveryCapability.RequestSupported);
        Assert.Equal("karma-forge:sample-submission-id", model.DiscoveryCapability.SourceRef);
        Assert.DoesNotContain("Icanpreneur", JsonSerializer.Serialize(model.DiscoveryCapability), StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("Deftform", JsonSerializer.Serialize(model.DiscoveryCapability), StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("MetaSurvey", JsonSerializer.Serialize(model.DiscoveryCapability), StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task RunsiteTourDispatchUnauthenticatedRedirectsToLogin()
    {
        using Fixture fixture = new(authenticated: false);
        fixture.Controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };

        IActionResult result = await fixture.Controller.RunsiteTourDispatch("redmond-dockyard-pack", CancellationToken.None);

        RedirectResult redirect = Assert.IsType<RedirectResult>(result);
        Assert.Equal("/login?next=%2Frunsites%2Fpacks%2Fredmond-dockyard-pack%2Ftour", redirect.Url);
    }

    [Fact]
    public async Task RunsiteTourDispatchUnknownPackReturnsNotFound()
    {
        using Fixture fixture = new(authenticated: true);
        fixture.Controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };
        fixture.Controller.ControllerContext.HttpContext.Request.Headers.Authorization = "Bearer desktop-access-token";

        IActionResult result = await fixture.Controller.RunsiteTourDispatch("not-a-pack", CancellationToken.None);

        Assert.IsType<NotFoundResult>(result);
    }

    [Fact]
    public async Task RunsiteTourDispatchEnforcesFreeWeeklyQuota()
    {
        using Fixture fixture = new(authenticated: true);
        fixture.Controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };
        fixture.Controller.ControllerContext.HttpContext.Request.Headers.Authorization = "Bearer desktop-access-token";

        IActionResult first = await fixture.Controller.RunsiteTourDispatch("redmond-dockyard-pack", CancellationToken.None);
        var firstRedirect = Assert.IsType<RedirectResult>(first);
        Assert.Equal("https://my.matterport.com/show/?m=ax2JhiPGk5P", firstRedirect.Url);
        Assert.Equal("1", fixture.Controller.Response.Headers["X-Runsite-Tour-Limit"].ToString());
        Assert.Equal("0", fixture.Controller.Response.Headers["X-Runsite-Tour-Remaining"].ToString());
        string firstRequestId = fixture.Controller.Response.Headers["X-Horizon-Artifact-Request-Id"].ToString();
        Assert.StartsWith("horizon-artifact-", firstRequestId, StringComparison.Ordinal);
        Assert.Equal($"/api/v1/horizons/artifact-requests/me/{firstRequestId}", fixture.Controller.Response.Headers["X-Horizon-Artifact-Request-Href"].ToString());

        IActionResult second = await fixture.Controller.RunsiteTourDispatch("everett-switchyard-pack", CancellationToken.None);
        ObjectResult problem = Assert.IsType<ObjectResult>(second);
        Assert.Equal(StatusCodes.Status429TooManyRequests, problem.StatusCode);
        var details = Assert.IsType<ProblemDetails>(problem.Value);
        Assert.Equal("3D-tour allowance is exhausted for this week.", details.Detail);
        IReadOnlyList<HorizonArtifactRequestReceipt> receipts = fixture.ArtifactRequestReceipts.ListRecent("runsite", "subject.dispatch", limit: 10);
        Assert.Equal(2, receipts.Count);
        Assert.Contains(receipts, receipt =>
            receipt.Status == "accepted"
            && receipt.SourceRef == "runsite:redmond-dockyard-pack"
            && receipt.Quota?.WeeklyUsed == 1);
        Assert.Contains(receipts, receipt =>
            receipt.Status == "blocked"
            && receipt.SourceRef == "runsite:everett-switchyard-pack"
            && receipt.BlockedReasons.Contains("artifact allowance"));
    }

    [Fact]
    public async Task RunsiteTourDispatchPersistsSharedArtifactReceiptWithoutDoubleConsumingQuota()
    {
        using Fixture fixture = new(authenticated: true);
        fixture.Controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };
        fixture.Controller.ControllerContext.HttpContext.Request.Headers.Authorization = "Bearer desktop-access-token";

        IActionResult result = await fixture.Controller.RunsiteTourDispatch("redmond-dockyard-pack", CancellationToken.None);

        Assert.IsType<RedirectResult>(result);
        HorizonArtifactRequestReceipt receipt = Assert.Single(fixture.ArtifactRequestReceipts.ListRecent("runsite", "subject.dispatch", limit: 10));
        Assert.Equal("accepted", receipt.Status);
        Assert.Equal("runsite-tour", receipt.CapabilityId);
        Assert.Equal("tour", receipt.ArtifactKind);
        Assert.Equal("runsite:redmond-dockyard-pack", receipt.SourceRef);
        Assert.Equal("private", receipt.Visibility);
        Assert.NotNull(receipt.Quota);
        Assert.Equal(1, receipt.Quota!.WeeklyUsed);
        Assert.Equal(0, receipt.Quota.WeeklyRemaining);
        Assert.Equal("free", receipt.Quota.AllowanceTier);
        Assert.Equal("free_weekly_allowance", receipt.Quota.EntitlementBasis);
        Assert.Equal("account", receipt.Quota.EntitlementScope);
    }

    [Fact]
    public async Task RunsiteTourDispatchEnforcesSupporterWeeklyQuota()
    {
        using Fixture fixture = new(authenticated: true);
        fixture.Controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };
        fixture.Controller.ControllerContext.HttpContext.Request.Headers.Authorization = "Bearer desktop-access-token";

        fixture.Billing.SyncMember(
            new Chummer.Run.Contracts.Billing.BrilliantDirectoriesMemberSyncRequest(
                UserId: "subject.dispatch",
                MemberId: "supporter-membership",
                Email: "dispatch@example.com",
                PlanKey: "supporter",
                PlanName: "Supporter",
                MembershipStatus: "active",
                SupporterActive: true,
                ObservedAtUtc: new DateTimeOffset(2026, 6, 24, 10, 0, 0, TimeSpan.Zero)),
            "sync-secret");

        for (int i = 0; i < 10; i++)
        {
            IActionResult result = await fixture.Controller.RunsiteTourDispatch("redmond-dockyard-pack", CancellationToken.None);
            Assert.IsType<RedirectResult>(result);
        }

        IActionResult eleventh = await fixture.Controller.RunsiteTourDispatch("everett-switchyard-pack", CancellationToken.None);
        ObjectResult problem = Assert.IsType<ObjectResult>(eleventh);
        Assert.Equal(StatusCodes.Status429TooManyRequests, problem.StatusCode);
        var details = Assert.IsType<ProblemDetails>(problem.Value);
        Assert.Equal("3D-tour allowance is exhausted for this week.", details.Detail);
    }

    [Fact]
    public async Task PropertyquarryPropertyTourDispatchUnauthenticatedRedirectsToLogin()
    {
        using Fixture fixture = new(authenticated: false);
        fixture.Controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };

        IActionResult result = await fixture.Controller.PropertyquarryPropertyTourDispatch("northbound-research-lab", CancellationToken.None);

        RedirectResult redirect = Assert.IsType<RedirectResult>(result);
        Assert.Equal("/login?next=%2Fpropertyquarry%2Fproperties%2Fnorthbound-research-lab%2Ftour", redirect.Url);
    }

    [Fact]
    public async Task PropertyquarryPropertyTourDispatchUnknownPropertyReturnsNotFound()
    {
        using Fixture fixture = new(
            authenticated: true,
            configureSettings: settings =>
            {
                settings["CHUMMER_HORIZON_PROPERTYQUARRY_CAPABILITY_PROPERTYQUARRY_TOUR_ENABLED"] = "true";
            });
        fixture.Controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };
        fixture.Controller.ControllerContext.HttpContext.Request.Headers.Authorization = "Bearer desktop-access-token";

        IActionResult result = await fixture.Controller.PropertyquarryPropertyTourDispatch("not-a-property", CancellationToken.None);

        Assert.IsType<NotFoundResult>(result);
    }

    [Fact]
    public async Task PropertyquarryPropertyTourDispatchEnforcesFreeWeeklyQuota()
    {
        using Fixture fixture = new(
            authenticated: true,
            configureSettings: settings =>
            {
                settings["CHUMMER_HORIZON_PROPERTYQUARRY_CAPABILITY_PROPERTYQUARRY_TOUR_ENABLED"] = "true";
                settings["CHUMMER_HORIZON_PROPERTYQUARRY_CAPABILITY_PROPERTYQUARRY_TOUR_FREE_WEEKLY_LIMIT"] = "1";
            });
        fixture.Controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };
        fixture.Controller.ControllerContext.HttpContext.Request.Headers.Authorization = "Bearer desktop-access-token";

        IActionResult first = await fixture.Controller.PropertyquarryPropertyTourDispatch("northbound-research-lab", CancellationToken.None);
        var firstRedirect = Assert.IsType<RedirectResult>(first);
        Assert.Equal("https://my.matterport.com/show/?m=ax2JhiPGk5P", firstRedirect.Url);
        Assert.StartsWith("horizon-artifact-", fixture.Controller.Response.Headers["X-Horizon-Artifact-Request-Id"].ToString(), StringComparison.Ordinal);

        IActionResult second = await fixture.Controller.PropertyquarryPropertyTourDispatch("shoreline-automation-factory", CancellationToken.None);
        ObjectResult problem = Assert.IsType<ObjectResult>(second);
        Assert.Equal(StatusCodes.Status429TooManyRequests, problem.StatusCode);
        var details = Assert.IsType<ProblemDetails>(problem.Value);
        Assert.Equal("3D-tour allowance is exhausted for this week.", details.Detail);
        IReadOnlyList<HorizonArtifactRequestReceipt> receipts = fixture.ArtifactRequestReceipts.ListRecent("propertyquarry", "subject.dispatch", limit: 10);
        Assert.Equal(2, receipts.Count);
        Assert.Contains(receipts, receipt =>
            receipt.Status == "accepted"
            && receipt.SourceRef == "propertyquarry:northbound-research-lab"
            && receipt.Quota?.WeeklyUsed == 1);
        Assert.Contains(receipts, receipt =>
            receipt.Status == "blocked"
            && receipt.SourceRef == "propertyquarry:shoreline-automation-factory"
            && receipt.BlockedReasons.Contains("artifact allowance"));
    }

    [Fact]
    public async Task PropertyquarryPropertyTourDispatchPersistsSharedArtifactReceiptWithoutDoubleConsumingQuota()
    {
        using Fixture fixture = new(
            authenticated: true,
            configureSettings: settings =>
            {
                settings["CHUMMER_HORIZON_PROPERTYQUARRY_CAPABILITY_PROPERTYQUARRY_TOUR_ENABLED"] = "true";
                settings["CHUMMER_HORIZON_PROPERTYQUARRY_CAPABILITY_PROPERTYQUARRY_TOUR_FREE_WEEKLY_LIMIT"] = "1";
            });
        fixture.Controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };
        fixture.Controller.ControllerContext.HttpContext.Request.Headers.Authorization = "Bearer desktop-access-token";

        IActionResult result = await fixture.Controller.PropertyquarryPropertyTourDispatch("northbound-research-lab", CancellationToken.None);

        Assert.IsType<RedirectResult>(result);
        HorizonArtifactRequestReceipt receipt = Assert.Single(fixture.ArtifactRequestReceipts.ListRecent("propertyquarry", "subject.dispatch", limit: 10));
        Assert.Equal("accepted", receipt.Status);
        Assert.Equal("propertyquarry-tour", receipt.CapabilityId);
        Assert.Equal("tour", receipt.ArtifactKind);
        Assert.Equal("propertyquarry:northbound-research-lab", receipt.SourceRef);
        Assert.Equal("private", receipt.Visibility);
        Assert.NotNull(receipt.Quota);
        Assert.Equal(1, receipt.Quota!.WeeklyUsed);
        Assert.Equal(0, receipt.Quota.WeeklyRemaining);
    }

    [Fact]
    public async Task PropertyquarryPropertyTourDispatchEnforcesSupporterWeeklyQuota()
    {
        using Fixture fixture = new(
            authenticated: true,
            configureSettings: settings =>
            {
                settings["CHUMMER_HORIZON_PROPERTYQUARRY_CAPABILITY_PROPERTYQUARRY_TOUR_ENABLED"] = "true";
                settings["CHUMMER_HORIZON_PROPERTYQUARRY_CAPABILITY_PROPERTYQUARRY_TOUR_FREE_WEEKLY_LIMIT"] = "0";
                settings["CHUMMER_HORIZON_PROPERTYQUARRY_CAPABILITY_PROPERTYQUARRY_TOUR_SUPPORTER_WEEKLY_LIMIT"] = "2";
            });
        fixture.Controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };
        fixture.Controller.ControllerContext.HttpContext.Request.Headers.Authorization = "Bearer desktop-access-token";

        fixture.Billing.SyncMember(
            new Chummer.Run.Contracts.Billing.BrilliantDirectoriesMemberSyncRequest(
                UserId: "subject.dispatch",
                MemberId: "supporter-membership",
                Email: "dispatch@example.com",
                PlanKey: "supporter",
                PlanName: "Supporter",
                MembershipStatus: "active",
                SupporterActive: true,
                ObservedAtUtc: new DateTimeOffset(2026, 6, 24, 10, 0, 0, TimeSpan.Zero)),
            "sync-secret");

        for (int i = 0; i < 2; i++)
        {
            IActionResult result = await fixture.Controller.PropertyquarryPropertyTourDispatch("northbound-research-lab", CancellationToken.None);
            Assert.IsType<RedirectResult>(result);
        }

        IReadOnlyList<HorizonArtifactRequestReceipt> acceptedReceipts = fixture.ArtifactRequestReceipts.ListRecent("propertyquarry", "subject.dispatch", limit: 10);
        Assert.Contains(acceptedReceipts, receipt =>
            receipt.Status == "accepted"
            && receipt.Quota?.AllowanceTier == "supporter"
            && receipt.Quota.EntitlementBasis == "supporter_weekly_allowance"
            && receipt.Quota.EntitlementScope == "account"
            && receipt.Quota.WeeklyLimit == 2);

        IActionResult third = await fixture.Controller.PropertyquarryPropertyTourDispatch("shoreline-automation-factory", CancellationToken.None);
        ObjectResult problem = Assert.IsType<ObjectResult>(third);
        Assert.Equal(StatusCodes.Status429TooManyRequests, problem.StatusCode);
        var details = Assert.IsType<ProblemDetails>(problem.Value);
        Assert.Equal("3D-tour allowance is exhausted for this week.", details.Detail);
    }

    [Fact]
    public async Task JackpointBriefingVideoDispatchUnauthenticatedRedirectsToLogin()
    {
        using Fixture fixture = new(authenticated: false);
        fixture.Controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };

        IActionResult result = await fixture.Controller.JackpointBriefingVideoDispatch("emerald-sprawl-briefing", CancellationToken.None);

        RedirectResult redirect = Assert.IsType<RedirectResult>(result);
        Assert.Equal("/login?next=%2Fjackpoint%2Fbriefings%2Femerald-sprawl-briefing%2Fvideo", redirect.Url);
    }

    [Fact]
    public async Task JackpointBriefingVideoDispatchUnknownBriefingReturnsNotFound()
    {
        using Fixture fixture = new(authenticated: true, configureSettings: settings =>
        {
            settings["CHUMMER_HORIZON_JACKPOINT_CAPABILITY_JACKPOINT_BRIEFING_VIDEO_ENABLED"] = "true";
            settings["CHUMMER_HORIZON_JACKPOINT_CAPABILITY_JACKPOINT_BRIEFING_VIDEO_FREE_WEEKLY_LIMIT"] = "1";
        });
        fixture.Controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };
        fixture.Controller.ControllerContext.HttpContext.Request.Headers.Authorization = "Bearer desktop-access-token";

        IActionResult result = await fixture.Controller.JackpointBriefingVideoDispatch("not-a-briefing", CancellationToken.None);

        Assert.IsType<NotFoundResult>(result);
    }

    [Fact]
    public async Task JackpointBriefingVideoDispatchEnforcesFreeWeeklyQuota()
    {
        using Fixture fixture = new(authenticated: true, configureSettings: settings =>
        {
            settings["CHUMMER_HORIZON_JACKPOINT_CAPABILITY_JACKPOINT_BRIEFING_VIDEO_ENABLED"] = "true";
            settings["CHUMMER_HORIZON_JACKPOINT_CAPABILITY_JACKPOINT_BRIEFING_VIDEO_FREE_WEEKLY_LIMIT"] = "1";
        });
        fixture.Controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };
        fixture.Controller.ControllerContext.HttpContext.Request.Headers.Authorization = "Bearer desktop-access-token";

        IActionResult first = await fixture.Controller.JackpointBriefingVideoDispatch("emerald-sprawl-briefing", CancellationToken.None);
        var firstRedirect = Assert.IsType<RedirectResult>(first);
        AssertProtectedMediaRedirect(firstRedirect.Url, "/media/horizons/jackpoint-90s-deepdive.mp4");
        Assert.StartsWith("horizon-artifact-", fixture.Controller.Response.Headers["X-Horizon-Artifact-Request-Id"].ToString(), StringComparison.Ordinal);

        IActionResult second = await fixture.Controller.JackpointBriefingVideoDispatch("dockyard-contact-dossier", CancellationToken.None);
        ObjectResult problem = Assert.IsType<ObjectResult>(second);
        Assert.Equal(StatusCodes.Status429TooManyRequests, problem.StatusCode);
        var details = Assert.IsType<ProblemDetails>(problem.Value);
        Assert.Equal("Briefing video allowance is exhausted for this week.", details.Detail);
        IReadOnlyList<HorizonArtifactRequestReceipt> receipts = fixture.ArtifactRequestReceipts.ListRecent("jackpoint", "subject.dispatch", limit: 10);
        Assert.Equal(2, receipts.Count);
        Assert.Contains(receipts, receipt =>
            receipt.Status == "accepted"
            && receipt.SourceRef == "jackpoint:emerald-sprawl-briefing"
            && receipt.Quota?.WeeklyUsed == 1);
        Assert.Contains(receipts, receipt =>
            receipt.Status == "blocked"
            && receipt.SourceRef == "jackpoint:dockyard-contact-dossier"
            && receipt.BlockedReasons.Contains("artifact allowance"));
    }

    [Fact]
    public async Task JackpointBriefingVideoDispatchPersistsSharedArtifactReceiptWithoutDoubleConsumingQuota()
    {
        using Fixture fixture = new(authenticated: true, configureSettings: settings =>
        {
            settings["CHUMMER_HORIZON_JACKPOINT_CAPABILITY_JACKPOINT_BRIEFING_VIDEO_ENABLED"] = "true";
            settings["CHUMMER_HORIZON_JACKPOINT_CAPABILITY_JACKPOINT_BRIEFING_VIDEO_FREE_WEEKLY_LIMIT"] = "1";
        });
        fixture.Controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };
        fixture.Controller.ControllerContext.HttpContext.Request.Headers.Authorization = "Bearer desktop-access-token";

        IActionResult result = await fixture.Controller.JackpointBriefingVideoDispatch("emerald-sprawl-briefing", CancellationToken.None);

        Assert.IsType<RedirectResult>(result);
        HorizonArtifactRequestReceipt receipt = Assert.Single(fixture.ArtifactRequestReceipts.ListRecent("jackpoint", "subject.dispatch", limit: 10));
        Assert.Equal("accepted", receipt.Status);
        Assert.Equal("jackpoint-briefing-video", receipt.CapabilityId);
        Assert.Equal("briefing_video", receipt.ArtifactKind);
        Assert.Equal("jackpoint:emerald-sprawl-briefing", receipt.SourceRef);
        Assert.Equal("private", receipt.Visibility);
        Assert.NotNull(receipt.Quota);
        Assert.Equal(1, receipt.Quota!.WeeklyUsed);
        Assert.Equal(0, receipt.Quota.WeeklyRemaining);
    }

    [Fact]
    public async Task RunbookPrimerExportDispatchUnauthenticatedRedirectsToLogin()
    {
        using Fixture fixture = new(authenticated: false);
        fixture.Controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };

        IActionResult result = await fixture.Controller.RunbookPrimerExportDispatch("new-runner-primer", CancellationToken.None);

        RedirectResult redirect = Assert.IsType<RedirectResult>(result);
        Assert.Equal("/login?next=%2Frunbook%2Fprimers%2Fnew-runner-primer%2Fexport", redirect.Url);
    }

    [Fact]
    public async Task RunbookPrimerExportDispatchUnknownPrimerReturnsNotFound()
    {
        using Fixture fixture = new(authenticated: true, configureSettings: settings =>
        {
            settings["CHUMMER_HORIZON_RUNBOOK_PRESS_CAPABILITY_RUNBOOK_EXPORT_ENABLED"] = "true";
            settings["CHUMMER_HORIZON_RUNBOOK_PRESS_CAPABILITY_RUNBOOK_EXPORT_FREE_WEEKLY_LIMIT"] = "1";
        });
        fixture.Controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };
        fixture.Controller.ControllerContext.HttpContext.Request.Headers.Authorization = "Bearer desktop-access-token";

        IActionResult result = await fixture.Controller.RunbookPrimerExportDispatch("not-a-primer", CancellationToken.None);

        Assert.IsType<NotFoundResult>(result);
    }

    [Fact]
    public async Task RunbookPrimerExportDispatchEnforcesFreeWeeklyQuota()
    {
        using Fixture fixture = new(authenticated: true, configureSettings: settings =>
        {
            settings["CHUMMER_HORIZON_RUNBOOK_PRESS_CAPABILITY_RUNBOOK_EXPORT_ENABLED"] = "true";
            settings["CHUMMER_HORIZON_RUNBOOK_PRESS_CAPABILITY_RUNBOOK_EXPORT_FREE_WEEKLY_LIMIT"] = "1";
        });
        fixture.Controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };
        fixture.Controller.ControllerContext.HttpContext.Request.Headers.Authorization = "Bearer desktop-access-token";

        IActionResult first = await fixture.Controller.RunbookPrimerExportDispatch("new-runner-primer", CancellationToken.None);
        var firstRedirect = Assert.IsType<RedirectResult>(first);
        AssertProtectedMediaRedirect(firstRedirect.Url, "/media/horizons/runbook-press-90s-deepdive.mp4");
        Assert.StartsWith("horizon-artifact-", fixture.Controller.Response.Headers["X-Horizon-Artifact-Request-Id"].ToString(), StringComparison.Ordinal);

        IActionResult second = await fixture.Controller.RunbookPrimerExportDispatch("gm-first-night-primer", CancellationToken.None);
        ObjectResult problem = Assert.IsType<ObjectResult>(second);
        Assert.Equal(StatusCodes.Status429TooManyRequests, problem.StatusCode);
        var details = Assert.IsType<ProblemDetails>(problem.Value);
        Assert.Equal("Runbook export allowance is exhausted for this week.", details.Detail);
        IReadOnlyList<HorizonArtifactRequestReceipt> receipts = fixture.ArtifactRequestReceipts.ListRecent("runbook-press", "subject.dispatch", limit: 10);
        Assert.Equal(2, receipts.Count);
        Assert.Contains(receipts, receipt =>
            receipt.Status == "accepted"
            && receipt.SourceRef == "runbook-press:new-runner-primer"
            && receipt.Quota?.WeeklyUsed == 1);
        Assert.Contains(receipts, receipt =>
            receipt.Status == "blocked"
            && receipt.SourceRef == "runbook-press:gm-first-night-primer"
            && receipt.BlockedReasons.Contains("artifact allowance"));
    }

    [Fact]
    public async Task RunbookPrimerExportDispatchPersistsSharedArtifactReceiptWithoutDoubleConsumingQuota()
    {
        using Fixture fixture = new(authenticated: true, configureSettings: settings =>
        {
            settings["CHUMMER_HORIZON_RUNBOOK_PRESS_CAPABILITY_RUNBOOK_EXPORT_ENABLED"] = "true";
            settings["CHUMMER_HORIZON_RUNBOOK_PRESS_CAPABILITY_RUNBOOK_EXPORT_FREE_WEEKLY_LIMIT"] = "1";
        });
        fixture.Controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };
        fixture.Controller.ControllerContext.HttpContext.Request.Headers.Authorization = "Bearer desktop-access-token";

        IActionResult result = await fixture.Controller.RunbookPrimerExportDispatch("new-runner-primer", CancellationToken.None);

        Assert.IsType<RedirectResult>(result);
        HorizonArtifactRequestReceipt receipt = Assert.Single(fixture.ArtifactRequestReceipts.ListRecent("runbook-press", "subject.dispatch", limit: 10));
        Assert.Equal("accepted", receipt.Status);
        Assert.Equal("runbook-export", receipt.CapabilityId);
        Assert.Equal("document_export", receipt.ArtifactKind);
        Assert.Equal("runbook-press:new-runner-primer", receipt.SourceRef);
        Assert.Equal("private", receipt.Visibility);
        Assert.NotNull(receipt.Quota);
        Assert.Equal(1, receipt.Quota!.WeeklyUsed);
        Assert.Equal(0, receipt.Quota.WeeklyRemaining);
    }

    [Fact]
    public async Task TablePulseDebriefDispatchPersistsSharedArtifactReceipt()
    {
        using Fixture fixture = new(authenticated: true, configureSettings: settings =>
        {
            settings["CHUMMER_HORIZON_TABLE_PULSE_CAPABILITY_TABLE_PULSE_DEBRIEF_ENABLED"] = "true";
            settings["CHUMMER_HORIZON_TABLE_PULSE_CAPABILITY_TABLE_PULSE_DEBRIEF_FREE_WEEKLY_LIMIT"] = "1";
        });
        fixture.Controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };
        fixture.Controller.ControllerContext.HttpContext.Request.Headers.Authorization = "Bearer desktop-access-token";

        IActionResult result = await fixture.Controller.TablePulseDebriefDispatch(CancellationToken.None);

        RedirectResult redirect = Assert.IsType<RedirectResult>(result);
        Assert.Equal("/account/work#aftermath-packages", redirect.Url);
        Assert.StartsWith("horizon-artifact-", fixture.Controller.Response.Headers["X-Horizon-Artifact-Request-Id"].ToString(), StringComparison.Ordinal);
        HorizonArtifactRequestReceipt receipt = Assert.Single(fixture.ArtifactRequestReceipts.ListRecent("table-pulse", "subject.dispatch", limit: 10));
        Assert.Equal("accepted", receipt.Status);
        Assert.Equal("table-pulse-debrief", receipt.CapabilityId);
        Assert.Equal("debrief_packet", receipt.ArtifactKind);
        Assert.Equal("table-pulse:live-and-aftermath", receipt.SourceRef);
        Assert.NotNull(receipt.Quota);
        Assert.Equal(1, receipt.Quota!.WeeklyUsed);
    }

    [Fact]
    public async Task BlackLedgerDigestDispatchPersistsSharedArtifactReceipt()
    {
        using Fixture fixture = new(authenticated: true, configureSettings: settings =>
        {
            settings["CHUMMER_HORIZON_BLACK_LEDGER_CAPABILITY_BLACK_LEDGER_DIGEST_ENABLED"] = "true";
            settings["CHUMMER_HORIZON_BLACK_LEDGER_CAPABILITY_BLACK_LEDGER_DIGEST_FREE_WEEKLY_LIMIT"] = "1";
        });
        fixture.Controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };
        fixture.Controller.ControllerContext.HttpContext.Request.Headers.Authorization = "Bearer desktop-access-token";

        IActionResult result = await fixture.Controller.BlackLedgerDigestDispatch("1", CancellationToken.None);

        RedirectResult redirect = Assert.IsType<RedirectResult>(result);
        Assert.Equal("/ledger/turns/1/newsreel.json", redirect.Url);
        HorizonArtifactRequestReceipt receipt = Assert.Single(fixture.ArtifactRequestReceipts.ListRecent("black-ledger", "subject.dispatch", limit: 10));
        Assert.Equal("accepted", receipt.Status);
        Assert.Equal("black-ledger-digest", receipt.CapabilityId);
        Assert.Equal("world_tick_digest", receipt.ArtifactKind);
        Assert.Equal("black-ledger:turn-1:digest", receipt.SourceRef);
        Assert.Equal(1, receipt.Quota?.WeeklyUsed);
    }

    [Fact]
    public async Task LedgerNewsroomEpisodePagePersistsAnonymousPublicSafeArtifactReceipt()
    {
        using Fixture fixture = new(authenticated: false);
        fixture.Controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };
        fixture.Controller.ControllerContext.HttpContext.Request.Path = "/ledger/newsroom/turn-1-newsreel";

        IActionResult result = await fixture.Controller.LedgerNewsroomEpisodePage("turn-1-newsreel", CancellationToken.None);

        ViewResult view = Assert.IsType<ViewResult>(result);
        BlackLedgerHubPageViewModel model = Assert.IsType<BlackLedgerHubPageViewModel>(view.Model);
        string requestId = fixture.Controller.Response.Headers["X-Horizon-Artifact-Request-Id"].ToString();
        Assert.StartsWith("horizon-artifact-", requestId, StringComparison.Ordinal);
        Assert.Equal($"/api/v1/public/horizons/artifact-requests/{requestId}", fixture.Controller.Response.Headers["X-Horizon-Artifact-Request-Href"].ToString());
        AssertProtectedMediaUrl(model.WorldTurnBriefing!.Broadcast!.VideoMp4Href, "/media/ledger/newsreels/turn-1-newsreel.mp4");
        IReadOnlyList<HorizonArtifactRequestReceipt> receipts = fixture.ArtifactRequestReceipts.ListRecent("black-ledger", limit: 10);
        HorizonArtifactRequestReceipt receipt = Assert.Single(receipts);
        Assert.Equal("accepted", receipt.Status);
        Assert.Equal("black-ledger-newsroom", receipt.CapabilityId);
        Assert.Equal("newsroom_bulletin", receipt.ArtifactKind);
        Assert.Equal("black-ledger:turn-1:newsroom", receipt.SourceRef);
        Assert.Equal("public_safe", receipt.Visibility);
        Assert.False(receipt.QuotaTracked);
        Assert.True(string.IsNullOrWhiteSpace(receipt.RequestedByUserId));
        Assert.Null(receipt.Quota);
    }

    [Fact]
    public async Task LedgerFactionPromoJsonSanitizesVendorTruthAndProtectsMedia()
    {
        using Fixture fixture = new(authenticated: false);
        fixture.Controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };
        fixture.Controller.ControllerContext.HttpContext.Request.Path = "/ledger/factions/ashline-circle/promo.json";

        IActionResult result = await fixture.Controller.LedgerFactionPromoJson("ashline-circle", CancellationToken.None);

        OkObjectResult ok = Assert.IsType<OkObjectResult>(result);
        using JsonDocument payload = JsonSerializer.SerializeToDocument(ok.Value);
        Assert.Equal("VERIFIED_PROVIDER", payload.RootElement.GetProperty("provider_status").GetString());
        Assert.Equal("verified_cinematic_faction_bulletin", payload.RootElement.GetProperty("render_mode").GetString());
        Assert.Equal("storyboard_fallback", payload.RootElement.GetProperty("fallback_render_mode").GetString());
        AssertProtectedMediaUrl(payload.RootElement.GetProperty("video_mp4_href").GetString(), "/media/ledger/factions/ashline-circle-promo-mobile.mp4");
        AssertProtectedMediaUrl(payload.RootElement.GetProperty("video_webm_href").GetString(), "/media/ledger/factions/ashline-circle-promo.webm");
        AssertProtectedMediaUrl(payload.RootElement.GetProperty("poster_href").GetString(), "/media/ledger/factions/ashline-circle-promo-poster.png");
        JsonElement capability = payload.RootElement.GetProperty("artifact_capability");
        Assert.Equal("black-ledger-faction-promo", capability.GetProperty("CapabilityId").GetString());
        Assert.Equal("faction_promo", capability.GetProperty("ArtifactKind").GetString());
        Assert.Equal("black-ledger:faction-ashline-circle:promo", capability.GetProperty("SourceRef").GetString());
        string serialized = JsonSerializer.Serialize(ok.Value);
        Assert.DoesNotContain("MagicFit", serialized, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task OriginDossierMediaDispatchPersistsSharedArtifactReceipt()
    {
        using Fixture fixture = new(authenticated: true, configureSettings: settings =>
        {
            settings["CHUMMER_HORIZON_ORIGIN_DOSSIER_CAPABILITY_ORIGIN_DOSSIER_MEDIA_ENABLED"] = "true";
            settings["CHUMMER_HORIZON_ORIGIN_DOSSIER_CAPABILITY_ORIGIN_DOSSIER_MEDIA_FREE_WEEKLY_LIMIT"] = "1";
        });
        fixture.Controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };
        fixture.Controller.ControllerContext.HttpContext.Request.Headers.Authorization = "Bearer desktop-access-token";

        IActionResult result = await fixture.Controller.OriginDossierMediaDispatch(CancellationToken.None);

        RedirectResult redirect = Assert.IsType<RedirectResult>(result);
        AssertProtectedMediaRedirect(redirect.Url, "/media/horizons/origin-dossier-the-name-she-chose-20260619.mp4");
        HorizonArtifactRequestReceipt receipt = Assert.Single(fixture.ArtifactRequestReceipts.ListRecent("origin-dossier", "subject.dispatch", limit: 10));
        Assert.Equal("accepted", receipt.Status);
        Assert.Equal("origin-dossier-media", receipt.CapabilityId);
        Assert.Equal("dossier_media", receipt.ArtifactKind);
        Assert.Equal("origin-dossier:public-story-packet", receipt.SourceRef);
        Assert.Equal(1, receipt.Quota?.WeeklyUsed);
    }

    [Fact]
    public async Task KarmaForgeDiscoveryPacketDispatchPersistsSharedArtifactReceipt()
    {
        using Fixture fixture = new(authenticated: true, configureSettings: settings =>
        {
            settings["CHUMMER_HORIZON_KARMA_FORGE_CAPABILITY_KARMA_FORGE_DISCOVERY_ENABLED"] = "true";
            settings["CHUMMER_HORIZON_KARMA_FORGE_CAPABILITY_KARMA_FORGE_DISCOVERY_FREE_WEEKLY_LIMIT"] = "1";
        });
        fixture.Controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };
        fixture.Controller.ControllerContext.HttpContext.Request.Headers.Authorization = "Bearer desktop-access-token";

        IActionResult result = await fixture.Controller.KarmaForgeDiscoveryPacketDispatch(CancellationToken.None);

        RedirectResult redirect = Assert.IsType<RedirectResult>(result);
        Assert.Equal("/participate/karma-forge", redirect.Url);
        HorizonArtifactRequestReceipt receipt = Assert.Single(fixture.ArtifactRequestReceipts.ListRecent("karma-forge", "subject.dispatch", limit: 10));
        Assert.Equal("accepted", receipt.Status);
        Assert.Equal("karma-forge-discovery", receipt.CapabilityId);
        Assert.Equal("discovery_packet", receipt.ArtifactKind);
        Assert.Equal("karma-forge:public-intake", receipt.SourceRef);
        Assert.Equal(1, receipt.Quota?.WeeklyUsed);
    }

    [Fact]
    public async Task RunsiteTourQuotaMeRequiresAuthentication()
    {
        using Fixture fixture = new(authenticated: false);
        fixture.Controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };

        IActionResult result = await fixture.Controller.RunsiteTourQuota(CancellationToken.None);

        ObjectResult problem = Assert.IsType<ObjectResult>(result);
        Assert.Equal(StatusCodes.Status401Unauthorized, problem.StatusCode);
    }

    [Fact]
    public async Task RunsiteTourQuotaMeReturnsCurrentUserAllowance()
    {
        using Fixture fixture = new(authenticated: true);
        fixture.Controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };
        fixture.Controller.ControllerContext.HttpContext.Request.Headers.Authorization = "Bearer desktop-access-token";

        IActionResult result = await fixture.Controller.RunsiteTourQuota(CancellationToken.None);
        OkObjectResult ok = Assert.IsType<OkObjectResult>(result);
        var quota = Assert.IsType<RunsiteTourQuotaSnapshot>(ok.Value);
        Assert.False(quota.SupporterActive);
        Assert.Equal("free", quota.AllowanceTier);
        Assert.Equal("free_weekly_allowance", quota.EntitlementBasis);
        Assert.Equal("account", quota.EntitlementScope);
        Assert.Equal(1, quota.WeeklyLimit);
        Assert.Equal(0, quota.WeeklyUsed);
        Assert.Equal(1, quota.WeeklyRemaining);
    }

    [Fact]
    public void RunsiteTourQuotaPersistsUsageAndResetsByWeek()
    {
        using Fixture fixture = new();
        var firstCapabilities = new HorizonCapabilityService(fixture.Configuration);
        var firstService = new RunsiteTourQuotaService(
            new HorizonArtifactQuotaService(new HorizonArtifactUsageStore(fixture.Configuration), firstCapabilities, fixture.Billing),
            firstCapabilities);
        DateTimeOffset firstWeek = new(2026, 6, 24, 10, 0, 0, TimeSpan.Zero);

        RunsiteTourQuotaSnapshot consumed = firstService.ConsumeTour("subject.persist", firstWeek, "persist@example.com");

        Assert.Equal(1, consumed.WeeklyUsed);
        Assert.Equal(0, consumed.WeeklyRemaining);

        var reloadedCapabilities = new HorizonCapabilityService(fixture.Configuration);
        var reloadedService = new RunsiteTourQuotaService(
            new HorizonArtifactQuotaService(new HorizonArtifactUsageStore(fixture.Configuration), reloadedCapabilities, fixture.Billing),
            reloadedCapabilities);
        RunsiteTourQuotaSnapshot sameWeek = reloadedService.GetQuota("subject.persist", firstWeek.AddDays(1), "persist@example.com");
        Assert.Equal(1, sameWeek.WeeklyUsed);
        Assert.Equal(0, sameWeek.WeeklyRemaining);

        RunsiteTourQuotaSnapshot nextWeek = reloadedService.GetQuota("subject.persist", firstWeek.AddDays(7), "persist@example.com");
        Assert.Equal(0, nextWeek.WeeklyUsed);
        Assert.Equal(1, nextWeek.WeeklyRemaining);
    }

    [Fact]
    public void RunsiteReceiptJsonReturnsSignedInPrepContract()
    {
        using Fixture fixture = new();

        IActionResult result = fixture.Controller.RunsiteReceiptJson();

        var ok = Assert.IsType<OkObjectResult>(result);
        using JsonDocument payload = JsonSerializer.SerializeToDocument(ok.Value);
        Assert.Equal("runsite", payload.RootElement.GetProperty("Horizon").GetString());
        Assert.Equal("shipped_mvp", payload.RootElement.GetProperty("Status").GetString());
        Assert.Equal("/runsites/packs/redmond-dockyard-pack.md", payload.RootElement.GetProperty("PublicBoard").GetProperty("FirstPackMarkdownHref").GetString());
        Assert.Equal("/runsites/packs/redmond-dockyard-pack.json", payload.RootElement.GetProperty("PublicBoard").GetProperty("FirstPackJsonHref").GetString());
        Assert.Equal("/account/runsites", payload.RootElement.GetProperty("SignedInBench").GetProperty("AccountEntryHref").GetString());
        Assert.Equal("/account/runsites/open", payload.RootElement.GetProperty("SignedInBench").GetProperty("AccountRedirectHref").GetString());
        Assert.Equal("/api/v1/campaign-spine/me/workspace-digests", payload.RootElement.GetProperty("SignedInBench").GetProperty("WorkspaceIndexApiHref").GetString());
        Assert.Equal("/api/v1/campaign-spine/me/runs", payload.RootElement.GetProperty("SignedInBench").GetProperty("RunIndexApiHref").GetString());
        JsonElement sharedArtifacts = payload.RootElement.GetProperty("SharedArtifacts");
        Assert.Equal("/api/v1/public/horizons/capabilities", sharedArtifacts.GetProperty("PublicCapabilityCatalogHref").GetString());
        Assert.Equal("/api/v1/public/horizons/capabilities?horizonId=runsite&artifactKindOrCapabilityId=runsite-tour", sharedArtifacts.GetProperty("PublicCapabilityHealthHref").GetString());
        Assert.Equal("/api/v1/horizons/capabilities/me?horizonId=runsite&artifactKindOrCapabilityId=runsite-tour", sharedArtifacts.GetProperty("SignedInCapabilityCatalogHref").GetString());
        Assert.Equal("/api/v1/horizons/quotas/me?horizonId=runsite&artifactKindOrCapabilityId=runsite-tour", sharedArtifacts.GetProperty("SignedInQuotaCatalogHref").GetString());
        Assert.Equal("/api/v1/horizons/artifact-requests/me?horizonId=runsite", sharedArtifacts.GetProperty("SignedInRequestReceiptHref").GetString());
        Assert.Equal("/api/v1/horizons/artifact-requests/me/{requestId}", sharedArtifacts.GetProperty("SignedInRequestReceiptDetailHrefTemplate").GetString());
        JsonElement capability = payload.RootElement.GetProperty("ArtifactCapability");
        Assert.Equal("runsite-tour", capability.GetProperty("CapabilityId").GetString());
        Assert.Equal("runsite:prep-network", capability.GetProperty("SourceRef").GetString());
        Assert.DoesNotContain("Matterport", JsonSerializer.Serialize(ok.Value), StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("3DVista", JsonSerializer.Serialize(ok.Value), StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void PropertyquarryReceiptJsonReturnsSignedInPropertyNetworkContract()
    {
        using Fixture fixture = new();

        IActionResult result = fixture.Controller.PropertyquarryReceiptJson();

        OkObjectResult ok = Assert.IsType<OkObjectResult>(result);
        using JsonDocument payload = JsonSerializer.SerializeToDocument(ok.Value);
        Assert.Equal("propertyquarry", payload.RootElement.GetProperty("Horizon").GetString());
        Assert.Equal("shipped_mvp", payload.RootElement.GetProperty("Status").GetString());
        Assert.Equal("/propertyquarry/properties/northbound-research-lab.md", payload.RootElement.GetProperty("PublicBoard").GetProperty("FirstPropertyMarkdownHref").GetString());
        Assert.Equal("/propertyquarry/properties/northbound-research-lab.json", payload.RootElement.GetProperty("PublicBoard").GetProperty("FirstPropertyJsonHref").GetString());
        Assert.Equal("/account/propertyquarry", payload.RootElement.GetProperty("SignedInDesk").GetProperty("AccountEntryHref").GetString());
        Assert.Equal("/account/propertyquarry/open", payload.RootElement.GetProperty("SignedInDesk").GetProperty("AccountRedirectHref").GetString());
        Assert.Equal("/account/propertyquarry/{propertyId}", payload.RootElement.GetProperty("SignedInDesk").GetProperty("AccountWorkspaceHrefTemplate").GetString());
        Assert.Equal("/api/v1/campaign-spine/me/property-workspaces/{propertyId}", payload.RootElement.GetProperty("SignedInDesk").GetProperty("PrepWorkspaceApiHrefTemplate").GetString());
        Assert.Equal("/api/v1/campaign-spine/me/property-continuity/{propertyId}", payload.RootElement.GetProperty("SignedInDesk").GetProperty("ContinuityApiHref").GetString());
        JsonElement sharedArtifacts = payload.RootElement.GetProperty("SharedArtifacts");
        Assert.Equal("/api/v1/public/horizons/capabilities", sharedArtifacts.GetProperty("PublicCapabilityCatalogHref").GetString());
        Assert.Equal("/api/v1/public/horizons/capabilities?horizonId=propertyquarry&artifactKindOrCapabilityId=propertyquarry-tour", sharedArtifacts.GetProperty("PublicCapabilityHealthHref").GetString());
        Assert.Equal("/api/v1/horizons/capabilities/me?horizonId=propertyquarry&artifactKindOrCapabilityId=propertyquarry-tour", sharedArtifacts.GetProperty("SignedInCapabilityCatalogHref").GetString());
        Assert.Equal("/api/v1/horizons/quotas/me?horizonId=propertyquarry&artifactKindOrCapabilityId=propertyquarry-tour", sharedArtifacts.GetProperty("SignedInQuotaCatalogHref").GetString());
        Assert.Equal("/api/v1/horizons/artifact-requests/me?horizonId=propertyquarry", sharedArtifacts.GetProperty("SignedInRequestReceiptHref").GetString());
        Assert.Equal("/api/v1/horizons/artifact-requests/me/{requestId}", sharedArtifacts.GetProperty("SignedInRequestReceiptDetailHrefTemplate").GetString());
        JsonElement capability = payload.RootElement.GetProperty("ArtifactCapability");
        Assert.Equal("propertyquarry-tour", capability.GetProperty("CapabilityId").GetString());
        Assert.Equal("propertyquarry:property-network", capability.GetProperty("SourceRef").GetString());
        Assert.DoesNotContain("Matterport", JsonSerializer.Serialize(ok.Value), StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("3DVista", JsonSerializer.Serialize(ok.Value), StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void KarmaForgeReceiptJsonReturnsDiscoveryAndSharedArtifactContract()
    {
        using Fixture fixture = new();

        IActionResult result = fixture.Controller.KarmaForgeReceiptJson();

        OkObjectResult ok = Assert.IsType<OkObjectResult>(result);
        using JsonDocument payload = JsonSerializer.SerializeToDocument(ok.Value);
        Assert.Equal("karma-forge", payload.RootElement.GetProperty("Horizon").GetString());
        Assert.Equal("shipped_mvp", payload.RootElement.GetProperty("Status").GetString());
        Assert.Equal("/participate/karma-forge", payload.RootElement.GetProperty("PublicBoard").GetProperty("IntakeHref").GetString());
        Assert.Equal("/participate/karma-forge/discovery", payload.RootElement.GetProperty("PublicBoard").GetProperty("DiscoveryDispatchHref").GetString());
        JsonElement sharedArtifacts = payload.RootElement.GetProperty("SharedArtifacts");
        Assert.Equal("/api/v1/public/horizons/capabilities", sharedArtifacts.GetProperty("PublicCapabilityCatalogHref").GetString());
        Assert.Null(sharedArtifacts.GetProperty("PublicCapabilityHealthHref").GetString());
        Assert.Equal("/api/v1/horizons/capabilities/me?horizonId=karma-forge&artifactKindOrCapabilityId=karma-forge-discovery", sharedArtifacts.GetProperty("SignedInCapabilityCatalogHref").GetString());
        Assert.Equal("/api/v1/horizons/quotas/me?horizonId=karma-forge&artifactKindOrCapabilityId=karma-forge-discovery", sharedArtifacts.GetProperty("SignedInQuotaCatalogHref").GetString());
        Assert.Equal("/api/v1/horizons/artifact-requests/me?horizonId=karma-forge", sharedArtifacts.GetProperty("SignedInRequestReceiptHref").GetString());
        Assert.Equal("/api/v1/horizons/artifact-requests/me/{requestId}", sharedArtifacts.GetProperty("SignedInRequestReceiptDetailHrefTemplate").GetString());
        JsonElement capability = payload.RootElement.GetProperty("ArtifactCapability");
        Assert.Equal("karma-forge-discovery", capability.GetProperty("CapabilityId").GetString());
        Assert.Equal("karma-forge:public-intake", capability.GetProperty("SourceRef").GetString());
        Assert.DoesNotContain("Icanpreneur", JsonSerializer.Serialize(ok.Value), StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("Deftform", JsonSerializer.Serialize(ok.Value), StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("MetaSurvey", JsonSerializer.Serialize(ok.Value), StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void AnarchyRuntimeReceiptJsonReturnsShippedRulesLightContract()
    {
        using Fixture fixture = new();

        IActionResult result = fixture.Controller.AnarchyRuntimeReceiptJson();

        var ok = Assert.IsType<OkObjectResult>(result);
        using JsonDocument payload = JsonSerializer.SerializeToDocument(ok.Value);
        Assert.Equal("anarchy", payload.RootElement.GetProperty("Horizon").GetString());
        Assert.Equal("shipped_mvp", payload.RootElement.GetProperty("Status").GetString());
        Assert.Equal("shadowrun_anarchy", payload.RootElement.GetProperty("RulesetId").GetString());
        Assert.Equal("/play/anarchy", payload.RootElement.GetProperty("PlayShell").GetProperty("PlayHref").GetString());
        Assert.Equal("/ledger/anarchy", payload.RootElement.GetProperty("PlayShell").GetProperty("LedgerHref").GetString());
        Assert.Equal("/anarchy/export/runner.json", payload.RootElement.GetProperty("ExportLane").GetProperty("ExportJsonHref").GetString());
        Assert.Equal("/anarchy/explain", payload.RootElement.GetProperty("ExportLane").GetProperty("ExplainReceiptHref").GetString());
        Assert.Equal("Shipped rules-light path", payload.RootElement.GetProperty("PublicProfile").GetProperty("VerdictLabel").GetString());
        Assert.True(payload.RootElement.GetProperty("DispatchLane").GetProperty("ReceiptAnchored").GetBoolean());
    }

    [Fact]
    public void GhostwireReplayReceiptJsonReturnsShippedAfterActionContract()
    {
        using Fixture fixture = new();

        IActionResult result = fixture.Controller.GhostwireReplayNetworkReceiptJson();

        var ok = Assert.IsType<OkObjectResult>(result);
        using JsonDocument payload = JsonSerializer.SerializeToDocument(ok.Value);
        Assert.Equal("ghostwire", payload.RootElement.GetProperty("Horizon").GetString());
        Assert.Equal("shipped_mvp", payload.RootElement.GetProperty("Status").GetString());
        Assert.Equal("/ghostwire/after-action/replay_timeline.md", payload.RootElement.GetProperty("PublicBoard").GetProperty("ReplayTimelineMarkdownHref").GetString());
        Assert.Equal("/ghostwire/after-action/replay_timeline.json", payload.RootElement.GetProperty("PublicBoard").GetProperty("ReplayTimelineJsonHref").GetString());
        Assert.Equal("/ghostwire/after-action/after_action_report.json", payload.RootElement.GetProperty("PublicBoard").GetProperty("AfterActionReportJsonHref").GetString());
        Assert.Equal("/ghostwire/after-action/consequence_chain.json", payload.RootElement.GetProperty("PublicBoard").GetProperty("ConsequenceChainJsonHref").GetString());
        Assert.Equal("Not claimed", payload.RootElement.GetProperty("Boundaries").GetProperty("TranscriptTruth").GetString());
    }

    [Fact]
    public async Task SignedInWorldTickValidationJsonReturnsReceiptBackedPacket()
    {
        using Fixture fixture = new(authenticated: true);
        fixture.Controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };
        fixture.Controller.ControllerContext.HttpContext.Request.Headers.Authorization = "Bearer desktop-access-token";
        var user = fixture.Accounts.EnsureUser("subject.dispatch", "Dispatch User", "dispatch@example.com");
        fixture.BlackLedgerFactions.JoinFaction(user, "ashline-circle");

        IActionResult result = await fixture.Controller.AccountLedgerWorldTickValidationJson(CancellationToken.None);

        var ok = Assert.IsType<OkObjectResult>(result);
        using JsonDocument payload = JsonSerializer.SerializeToDocument(ok.Value);
        Assert.Equal("emerald-sprawl-prelude", payload.RootElement.GetProperty("WorldId").GetString());
        Assert.Equal(1, payload.RootElement.GetProperty("ToTurn").GetInt32());
        Assert.True(payload.RootElement.GetProperty("Checks").GetArrayLength() >= 3);
        Assert.Contains(
            payload.RootElement.GetProperty("Links").EnumerateArray().Select(item => item.GetString()),
            item => string.Equals(item, "/account/ledger/factions/ashline-circle/leader-briefing", StringComparison.Ordinal));
        JsonElement capability = payload.RootElement.GetProperty("ArtifactCapability");
        Assert.Equal("black-ledger-digest", capability.GetProperty("CapabilityId").GetString());
        Assert.Equal("black-ledger:turn-1:validation", capability.GetProperty("SourceRef").GetString());
        Assert.DoesNotContain("Emailit", JsonSerializer.Serialize(ok.Value), StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("Signitic", JsonSerializer.Serialize(ok.Value), StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("vidBoard", JsonSerializer.Serialize(ok.Value), StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task SignedInLeaderBriefingJsonReturnsFactionSpecificDigest()
    {
        using Fixture fixture = new(authenticated: true);
        fixture.Controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };
        fixture.Controller.ControllerContext.HttpContext.Request.Headers.Authorization = "Bearer desktop-access-token";
        var user = fixture.Accounts.EnsureUser("subject.dispatch", "Dispatch User", "dispatch@example.com");
        fixture.BlackLedgerFactions.JoinFaction(user, "ashline-circle");

        IActionResult result = await fixture.Controller.AccountLedgerFactionLeaderBriefingJson("ashline-circle", CancellationToken.None);

        var ok = Assert.IsType<OkObjectResult>(result);
        using JsonDocument payload = JsonSerializer.SerializeToDocument(ok.Value);
        Assert.Equal("ashline-circle", payload.RootElement.GetProperty("FactionId").GetString());
        Assert.Equal("Ashline Circle", payload.RootElement.GetProperty("PublicName").GetString());
        Assert.True(payload.RootElement.GetProperty("PressureCalls").GetArrayLength() > 0);
        Assert.True(payload.RootElement.GetProperty("RecommendedActions").GetArrayLength() > 0);
    }

    [Fact]
    public async Task UnauthenticatedValidationRouteRedirectsToLogin()
    {
        using Fixture fixture = new(authenticated: false);

        IActionResult result = await fixture.Controller.AccountLedgerWorldTickValidationPage(CancellationToken.None);

        var redirect = Assert.IsType<RedirectResult>(result);
        Assert.Equal("/login?next=%2Faccount%2Fledger%2Fworldtick%2Fvalidation", redirect.Url);
    }

    [Fact]
    public async Task LeaderBriefingJsonForWrongFactionIsForbidden()
    {
        using Fixture fixture = new(authenticated: true);
        fixture.Controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };
        fixture.Controller.ControllerContext.HttpContext.Request.Headers.Authorization = "Bearer desktop-access-token";
        var user = fixture.Accounts.EnsureUser("subject.dispatch", "Dispatch User", "dispatch@example.com");
        fixture.BlackLedgerFactions.JoinFaction(user, "ashline-circle");

        IActionResult result = await fixture.Controller.AccountLedgerFactionLeaderBriefingJson("glass-tower-compact", CancellationToken.None);

        Assert.IsType<ForbidResult>(result);
    }

    private sealed class Fixture : IDisposable
    {
        private readonly string _root;

        public Fixture(
            bool authenticated = false,
            string? runtimeManifestJson = null,
            Action<Dictionary<string, string?>>? configureSettings = null)
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
                ["CHUMMER_BRILLIANT_DIRECTORIES_BILLING_STORE_PATH"] = Path.Combine(_root, "billing.json"),
                ["CHUMMER_MYFIRSTBOOK_USAGE_STORE_PATH"] = Path.Combine(_root, "myfirstbook-usage-store.json"),
                ["CHUMMER_RUNSITE_TOUR_USAGE_STORE_PATH"] = Path.Combine(_root, "runsite-tour-usage-store.json"),
                ["CHUMMER_HORIZON_ARTIFACT_REQUEST_RECEIPT_STORE_PATH"] = Path.Combine(_root, "horizon-artifact-request-receipts.json"),
                ["BRILLIANT_DIRECTORIES_SUPPORTER_PLAN_URL"] = "https://billing.example.test/supporter",
                ["BRILLIANT_DIRECTORIES_SYNC_SECRET"] = "sync-secret",
                ["CHUMMER_COMMUNITY_STORE_PATH"] = Path.Combine(_root, "community-store.json"),
                ["CHUMMER_KARMA_FORGE_STORE_PATH"] = Path.Combine(_root, "karma-forge-store.json"),
                ["IDENTITY_SERVICE_BASE_URL"] = "http://identity.example"
            };
            if (!string.IsNullOrWhiteSpace(runtimeManifestJson))
            {
                settings["CHUMMER_RELEASE_REGISTRY_CURRENT_URL"] = "https://registry.local/api/v1/registry/release-channel/current";
            }

            configureSettings?.Invoke(settings);

            Configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(settings)
                .Build();

            HttpClient? runtimeManifestClient = string.IsNullOrWhiteSpace(runtimeManifestJson)
                ? null
                : new HttpClient(new StaticJsonHandler(runtimeManifestJson));
            ManifestService = new PublicReleaseManifestService(Configuration, runtimeManifestClient);
            PublicCanonFileLoader canon = new(Configuration);
            ReleaseSelection = new ReleaseSelectionService(canon);
            HubIdentityClient identity = new(
                new HttpClient(new IdentityHandler(authenticated))
                {
                    BaseAddress = new Uri("http://identity.example")
                },
                Configuration,
                NullLogger<HubIdentityClient>.Instance);
            Identity = identity;
            PublicLandingService landing = new(canon, new PublicActionResolver());
            PublicNavigationService navigation = new(canon, new PublicRouteCatalogService(canon));
            HubPageChromeService chrome = new(landing, navigation, ManifestService, ReleaseSelection, new HttpContextAccessor());
            PublicTrustPulseService trustPulse = new(
                new WeeklyProductPulseArtifactService(Configuration, NullLogger<WeeklyProductPulseArtifactService>.Instance),
                Configuration,
                NullLogger<PublicTrustPulseService>.Instance);
            CommunityStore communityStore = new(Configuration, NullLogger<CommunityStore>.Instance);
            Accounts = new AccountService(communityStore);
            WorkspaceLifecyclePolicyService workspaceLifecycle = new(Configuration);
            CampaignArtifactRegistryBridge artifactRegistry = new(communityStore);
            CampaignSpineService campaignSpine = new(communityStore, workspaceLifecycle, artifactRegistry);
            BlackLedgerPublicStatsService blackLedgerStats = new(Configuration);
            BlackLedgerDispatchService blackLedgerDispatches = new(communityStore, blackLedgerStats, NullLogger<BlackLedgerDispatchService>.Instance);
            BlackLedgerFactions = new BlackLedgerFactionOnboardingService(Configuration, blackLedgerStats, campaignSpine, communityStore);
            BlackLedgerWorldTickBriefingService blackLedgerBriefings = new(blackLedgerStats, BlackLedgerFactions);
            BlackLedgerTickNewsNotificationService blackLedgerTickNews = new(
                new HttpClient(new StaticJsonHandler("""{"ok":true}""")),
                communityStore,
                Configuration,
                new BlackLedgerNewsRecipientResolver(communityStore, Configuration),
                blackLedgerBriefings,
                BlackLedgerFactions,
                NullLogger<BlackLedgerTickNewsNotificationService>.Instance);
            BlackLedgerAdvisoryService blackLedgerAdvisories = new(
                new HttpClient(new StaticJsonHandler("""{"target_ref":"delivery-test"}""")),
                communityStore,
                Configuration,
                BlackLedgerFactions,
                NullLogger<BlackLedgerAdvisoryService>.Instance);
            AnarchyPreviewService anarchyPreview = new(blackLedgerDispatches);
            BrilliantDirectoriesBillingStore brilliantDirectoriesBillingStore = new(Configuration);
            MyFirstBookUsageStore myFirstBookUsageStore = new(Configuration);
            BrilliantDirectoriesBillingService brilliantDirectoriesBilling = new(brilliantDirectoriesBillingStore, myFirstBookUsageStore, Configuration);
            HorizonCapabilityService horizonCapabilities = new(Configuration);
            HorizonArtifactQuotaService horizonArtifactQuota = new(new HorizonArtifactUsageStore(Configuration), horizonCapabilities, brilliantDirectoriesBilling);
            HorizonArtifactQuota = horizonArtifactQuota;
            ArtifactRequestReceipts = new HorizonArtifactRequestReceiptStore(Configuration);
            HorizonArtifactRequestService artifactRequests = new(horizonCapabilities, horizonArtifactQuota, ArtifactRequestReceipts);
            RunsiteTourQuotaService runsiteTourQuota = new(horizonArtifactQuota, horizonCapabilities);
            ParticipationOperatorNotificationService participationNotifications = new(
                new HttpClient(new StaticJsonHandler("""{"target_ref":"delivery-test"}""")),
                communityStore,
                Configuration,
                NullLogger<ParticipationOperatorNotificationService>.Instance);
            BeHumanEventAdapterPostureService beHumanPosture = new(Configuration);
            IGmSessionVenueAdapter gmVenueAdapter = new BeHumanGmSessionVenueAdapter(new StaticHttpClientFactory(new HttpClient(new StaticJsonHandler("""{}"""))), Configuration, beHumanPosture);
            GmSessionVenueService gmSessionVenues = new(new GmSessionVenueStore(Configuration), beHumanPosture, gmVenueAdapter, Configuration, communityStore);
            AnswerlyRuntimePolicy answerlyPolicy = new(Configuration);
            BuildGhostConciergeService buildGhostConcierge = new(
                Configuration,
                answerlyPolicy,
                new AnswerlyHumanizerAdapter(answerlyPolicy, new RuleSafeOutputGate()));
            InstallLinkingStore = new InstallLinkingStore(Configuration, NullLogger<InstallLinkingStore>.Instance);
            InstallLinking = new InstallLinkingService(InstallLinkingStore, Configuration);
            IDataProtectionProvider dataProtectionProvider = DataProtectionProvider.Create(new DirectoryInfo(Path.Combine(_root, "keys")));
            InstallBootstrapTickets = new InstallBootstrapTicketService(dataProtectionProvider, Configuration);
            PersonalizedInstallScripts = new PersonalizedInstallScriptService(InstallLinkingStore, Configuration);
            HorizonArtifactAccessTokenService artifactAccessTokens = new(dataProtectionProvider, Configuration);
            HubPublicationDraftService draftService = new();
            PublicCreatorPublicationDiscoveryService publicCreatorDiscovery = new(Accounts, campaignSpine, draftService);
            CommunityCreatorHorizonsService communityCreatorHorizons = new(communityStore, InstallLinkingStore, publicCreatorDiscovery);
            WaveEightHorizonsService waveEightHorizons = new(communityStore, anarchyPreview);
            MediaArtifactHorizonsService mediaHorizons = new(Configuration, horizonCapabilities);
            Controller = new PublicLandingController(
                landing: landing,
                flipLinkDocumentPortal: new FlipLinkDocumentPortalService(Configuration),
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
                runsiteTourQuota: runsiteTourQuota,
                installLinking: InstallLinking,
                campaignSpine: campaignSpine,
                workspaceServerPlane: null!,
                readyForTonight: null!,
                knowledgeFabric: null!,
                nexusPan: null!,
                mediaHorizons: mediaHorizons,
                communityCreatorHorizons: communityCreatorHorizons,
                waveEightHorizons: waveEightHorizons,
                karmaForge: new KarmaForgeDiscoveryService(new KarmaForgeStore(Configuration, NullLogger<KarmaForgeStore>.Instance), Configuration),
                buildGhostConcierge: buildGhostConcierge,
                blackLedgerStats: blackLedgerStats,
                blackLedgerDispatches: blackLedgerDispatches,
                blackLedgerTickNews: blackLedgerTickNews,
                blackLedgerFactions: BlackLedgerFactions,
                blackLedgerAdvisories: blackLedgerAdvisories,
                blackLedgerBriefings: blackLedgerBriefings,
                beHumanEventAdapterPosture: new BeHumanEventAdapterPostureService(Configuration),
                gmSessionVenues: gmSessionVenues,
                anarchyPreview: anarchyPreview,
                packageCatalog: new PublicPackageCatalogService(),
                publicCreatorDiscovery: publicCreatorDiscovery,
                chrome: chrome,
                trustContent: null!,
                privacyBoundaries: null!,
                signalProjection: null!,
                signalOperations: null!,
                trustPulse: trustPulse,
                signedInTrustStatus: null!,
                supportCases: null!,
                supportPresentation: null!,
                configuration: Configuration,
                installBootstrapTickets: InstallBootstrapTickets,
                personalizedInstallScripts: PersonalizedInstallScripts,
                releaseUploadTickets: null!,
                windowsProofInstallers: new WindowsProofInstallerService(Configuration),
                aurPackages: new AurPackageCatalogService(Configuration),
                webHostEnvironment: null!,
                logger: NullLogger<PublicLandingController>.Instance,
                artifactRequests: artifactRequests,
                artifactAccessTokens: artifactAccessTokens);
            Billing = brilliantDirectoriesBilling;
        }

        public IConfiguration Configuration { get; }

        public AccountService Accounts { get; }

        public HubIdentityClient Identity { get; }

        public PublicReleaseManifestService ManifestService { get; }

        public ReleaseSelectionService ReleaseSelection { get; }

        public InstallLinkingService InstallLinking { get; }

        public InstallLinkingStore InstallLinkingStore { get; }

        public InstallBootstrapTicketService InstallBootstrapTickets { get; }

        public PersonalizedInstallScriptService PersonalizedInstallScripts { get; }

        public BlackLedgerFactionOnboardingService BlackLedgerFactions { get; }

        public HorizonArtifactQuotaService HorizonArtifactQuota { get; }

        public PublicLandingController Controller { get; }
        public BrilliantDirectoriesBillingService Billing { get; }
        public HorizonArtifactRequestReceiptStore ArtifactRequestReceipts { get; }

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

        private sealed class StaticHttpClientFactory : IHttpClientFactory
        {
            private readonly HttpClient _client;

            public StaticHttpClientFactory(HttpClient client)
            {
                _client = client;
            }

            public HttpClient CreateClient(string name) => _client;
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
