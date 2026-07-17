using System.Net;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using Chummer.Hub.Registry.Contracts.InstallLinking;
using Chummer.Run.Api.Controllers;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.Services.InstallLinking;
using Chummer.Run.Api.Services.Support;
using Chummer.Run.Contracts.Identity;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class InstallLinkingControllerBrowserCallbackTests
{
    [Fact]
    public async Task Browser_install_link_redirects_unauthenticated_requests_to_login_with_return_path()
    {
        using Fixture fixture = new(authenticated: false);
        fixture.Controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };
        fixture.Controller.ControllerContext.HttpContext.Request.Path = "/account/access/install-link";
        fixture.Controller.ControllerContext.HttpContext.Request.QueryString = new QueryString(
            "?installationId=ins-unauth&headId=avalonia&platform=windows&arch=x64&installLinkCallbackUri=chummer%3A%2F%2Finstall-link");

        IActionResult result = await fixture.Controller.BrowserInstallLink(
            installationId: "ins-unauth",
            headId: "avalonia",
            applicationVersion: "6.0.1-preview",
            releaseChannel: "preview",
            platform: "windows",
            arch: "x64",
            installLinkCallbackUri: "chummer://install-link",
            cancellationToken: CancellationToken.None);

        RedirectResult redirect = Assert.IsType<RedirectResult>(result);
        Assert.StartsWith("/login?next=", redirect.Url, StringComparison.Ordinal);
        Assert.Contains("%2Faccount%2Faccess%2Finstall-link%3FinstallationId%3Dins-unauth", redirect.Url, StringComparison.Ordinal);
        AssertSensitiveResponseHeaders(fixture.Controller.Response.Headers);
    }

    [Fact]
    public async Task Browser_install_link_login_return_path_does_not_relay_hostile_credentials()
    {
        using Fixture fixture = new(authenticated: false);
        fixture.Controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };
        fixture.Controller.ControllerContext.HttpContext.Request.Path = "/account/access/install-link";
        fixture.Controller.ControllerContext.HttpContext.Request.QueryString = new QueryString(
            "?accessToken=top-secret&ticket=top-ticket&claimCode=top-claim&apiKey=top-key");

        IActionResult result = await fixture.Controller.BrowserInstallLink(
            installationId: "ins-safe",
            headId: "avalonia",
            applicationVersion: "6.0.1-preview",
            releaseChannel: "preview",
            platform: "windows",
            arch: "x64",
            installLinkCallbackUri: "http://127.0.0.1:47761/install-link/callback?state=desktop&nonce=callback-proof&accessToken=nested-secret&unknown=nested-unknown#ticket=fragment-ticket",
            cancellationToken: CancellationToken.None);

        RedirectResult redirect = Assert.IsType<RedirectResult>(result);
        string decoded = redirect.Url!;
        for (int pass = 0; pass < 8; pass++)
        {
            decoded = Uri.UnescapeDataString(decoded);
        }

        Assert.Contains("installationId=ins-safe", decoded, StringComparison.Ordinal);
        Assert.Contains("state=desktop", decoded, StringComparison.Ordinal);
        Assert.DoesNotContain("top-secret", decoded, StringComparison.Ordinal);
        Assert.DoesNotContain("top-ticket", decoded, StringComparison.Ordinal);
        Assert.DoesNotContain("top-claim", decoded, StringComparison.Ordinal);
        Assert.DoesNotContain("top-key", decoded, StringComparison.Ordinal);
        Assert.DoesNotContain("nested-secret", decoded, StringComparison.Ordinal);
        Assert.DoesNotContain("nested-unknown", decoded, StringComparison.Ordinal);
        Assert.DoesNotContain("fragment-ticket", decoded, StringComparison.Ordinal);
    }

    [Theory]
    [InlineData("https://evil.example/install-link")]
    [InlineData("chummer://downloads")]
    [InlineData("http://127.0.0.1:47761/browser-only/claim?state=desktop")]
    [InlineData("https://localhost:47762/account/access/install-link")]
    public async Task Browser_install_link_rejects_invalid_callback_uris(string callbackUri)
    {
        using Fixture fixture = new(authenticated: false);
        fixture.Controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };
        fixture.Controller.ControllerContext.HttpContext.Request.Path = "/account/access/install-link";

        IActionResult result = await fixture.Controller.BrowserInstallLink(
            installationId: "ins-invalid",
            headId: "avalonia",
            applicationVersion: "6.0.1-preview",
            releaseChannel: "preview",
            platform: "windows",
            arch: "x64",
            installLinkCallbackUri: callbackUri,
            cancellationToken: CancellationToken.None);

        ObjectResult problem = Assert.IsType<ObjectResult>(result);
        Assert.Equal(StatusCodes.Status400BadRequest, problem.StatusCode);
        ProblemDetails details = Assert.IsType<ProblemDetails>(problem.Value);
        Assert.Equal("install-link callback uri is invalid.", details.Detail);
        AssertSensitiveResponseHeaders(fixture.Controller.Response.Headers);
    }

    [Fact]
    public async Task Browser_install_link_renders_authenticated_handoff_page_with_callback_code()
    {
        using Fixture fixture = new(authenticated: true);
        fixture.Controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };
        fixture.Controller.ControllerContext.HttpContext.Request.Path = "/account/access/install-link";
        fixture.Controller.ControllerContext.HttpContext.Request.Headers.Authorization = "Bearer desktop-access-token";

        IActionResult result = await fixture.Controller.BrowserInstallLink(
            installationId: "ins-browser-route",
            headId: "avalonia",
            applicationVersion: "6.0.1-preview",
            releaseChannel: "preview",
            platform: "windows",
            arch: "x64",
            installLinkCallbackUri: "chummer://install-link",
            cancellationToken: CancellationToken.None);

        ContentResult page = Assert.IsType<ContentResult>(result);
        Assert.Equal(StatusCodes.Status200OK, page.StatusCode);
        Assert.Contains("Claim this copy in Chummer", page.Content, StringComparison.Ordinal);
        Assert.Contains("Claim this copy", page.Content, StringComparison.Ordinal);
        Assert.Contains("Installer:", page.Content, StringComparison.Ordinal);
        Assert.Contains("id=\"install-link-open\"", page.Content, StringComparison.Ordinal);
        Assert.Contains("Claim link", page.Content, StringComparison.Ordinal);
        Assert.Contains("Copy claim link", page.Content, StringComparison.Ordinal);
        Assert.DoesNotContain("Manual launch link", page.Content, StringComparison.Ordinal);
        Assert.DoesNotContain("Open Chummer to finish linking this install", page.Content, StringComparison.Ordinal);
        Assert.DoesNotContain("Package:", page.Content, StringComparison.Ordinal);
        Assert.Contains("window.location.assign(href)", page.Content, StringComparison.Ordinal);
        Assert.Contains("iframe", page.Content, StringComparison.Ordinal);
        Assert.True(TryExtractPrimaryHref(page.Content!, out string callbackHref), "The controller should render a manual callback link.");
        Assert.True(Uri.TryCreate(WebUtility.HtmlDecode(callbackHref), UriKind.Absolute, out Uri? callbackUri), "The controller should emit a valid callback URI.");
        Assert.Equal("chummer", callbackUri.Scheme);
        Assert.Equal("install-link", callbackUri.Host);
        Assert.Contains("code=", callbackHref, StringComparison.Ordinal);
        Assert.Contains("installationId=ins-browser-route", callbackHref, StringComparison.Ordinal);
        Assert.Contains("headId=avalonia", callbackHref, StringComparison.Ordinal);
        Assert.Contains("installLinkMode=browser_callback", callbackHref, StringComparison.Ordinal);
        Assert.Contains("installLinkTransport=grant_callback", callbackHref, StringComparison.Ordinal);

        InstallBrowserCallbackDto callback = Assert.Single(fixture.Store.BrowserCallbacksById.Values);
        Assert.Equal("ins-browser-route", callback.InstallationId);
        Assert.Equal(InstallBrowserCallbackStates.Pending, callback.Status);
        Assert.Contains($"code={Uri.EscapeDataString(callback.CallbackCode)}", callbackHref, StringComparison.Ordinal);
        AssertSensitiveResponseHeaders(fixture.Controller.Response.Headers);
    }

    [Fact]
    public async Task Install_linking_api_success_applies_private_no_store_response_headers()
    {
        using Fixture fixture = new(authenticated: true);
        fixture.Controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };
        fixture.Controller.ControllerContext.HttpContext.Request.Path = "/api/v1/install-linking/me";
        fixture.Controller.ControllerContext.HttpContext.Request.Headers.Authorization = "Bearer desktop-access-token";

        ActionResult<InstallLinkingSummaryDto> result = await fixture.Controller.GetSummary(CancellationToken.None);

        Assert.IsType<OkObjectResult>(result.Result);
        AssertSensitiveResponseHeaders(fixture.Controller.Response.Headers);
    }

    [Fact]
    public void Install_linking_api_error_applies_private_no_store_response_headers()
    {
        using Fixture fixture = new(authenticated: false);
        fixture.Controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };
        fixture.Controller.ControllerContext.HttpContext.Request.Path = "/api/v1/install-linking/redeem";

        ActionResult<RedeemInstallClaimResponseDto> result = fixture.Controller.Redeem(request: null);

        Assert.IsType<BadRequestObjectResult>(result.Result);
        AssertSensitiveResponseHeaders(fixture.Controller.Response.Headers);
    }

    [Theory]
    [InlineData("http://127.0.0.1:47761/install-link/callback?state=desktop&nonce=callback-proof", "127.0.0.1", "/install-link/callback", true)]
    [InlineData("http://[::1]:47763/install-link/callback?state=desktop", "[::1]", "/install-link/callback", true)]
    [InlineData("http://127.0.0.1:47761/install-link/callback/?state=desktop", "127.0.0.1", "/install-link/callback/", true)]
    [InlineData("https://localhost:47762/install-link/callback", "localhost", "/install-link/callback", false)]
    public async Task Browser_install_link_preserves_app_local_callback_targets(
        string callbackUri,
        string expectedHost,
        string expectedPath,
        bool expectDesktopState)
    {
        using Fixture fixture = new(authenticated: true);
        fixture.Controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };
        fixture.Controller.ControllerContext.HttpContext.Request.Path = "/account/access/install-link";
        fixture.Controller.ControllerContext.HttpContext.Request.Headers.Authorization = "Bearer desktop-access-token";

        IActionResult result = await fixture.Controller.BrowserInstallLink(
            installationId: "ins-local-callback",
            headId: "avalonia",
            applicationVersion: "6.0.1-preview",
            releaseChannel: "preview",
            platform: "windows",
            arch: "x64",
            installLinkCallbackUri: callbackUri,
            cancellationToken: CancellationToken.None);

        ContentResult page = Assert.IsType<ContentResult>(result);
        Assert.Equal(StatusCodes.Status200OK, page.StatusCode);
        Assert.Contains("Claim this copy", page.Content, StringComparison.Ordinal);
        Assert.DoesNotContain("Open Chummer to finish linking this install", page.Content, StringComparison.Ordinal);
        Assert.DoesNotContain("Manual callback link", page.Content, StringComparison.Ordinal);
        Assert.Contains("Claim link", page.Content, StringComparison.Ordinal);
        Assert.Contains("Copy claim link", page.Content, StringComparison.Ordinal);
        Assert.DoesNotContain("iframe", page.Content, StringComparison.Ordinal);
        Assert.True(TryExtractPrimaryHref(page.Content!, out string callbackHref), "The controller should render a manual callback link.");
        string decodedCallbackHref = WebUtility.HtmlDecode(callbackHref);
        Assert.True(Uri.TryCreate(decodedCallbackHref, UriKind.Absolute, out Uri? redirectUri), "The controller should emit a valid app-local callback URI.");
        Assert.Equal(expectedHost, redirectUri.Host);
        Assert.Equal(expectedPath, redirectUri.AbsolutePath);
        Assert.Contains("code=", decodedCallbackHref, StringComparison.Ordinal);
        if (expectDesktopState)
        {
            Assert.Contains("state=desktop", decodedCallbackHref, StringComparison.Ordinal);
            if (callbackUri.Contains("nonce=callback-proof", StringComparison.Ordinal))
            {
                Assert.Contains("nonce=callback-proof", decodedCallbackHref, StringComparison.Ordinal);
            }
        }

        Assert.Contains("installationId=ins-local-callback", decodedCallbackHref, StringComparison.Ordinal);
        Assert.Contains("installLinkMode=browser_callback", decodedCallbackHref, StringComparison.Ordinal);
        Assert.Contains("installLinkTransport=grant_callback", decodedCallbackHref, StringComparison.Ordinal);

        InstallBrowserCallbackDto callback = Assert.Single(fixture.Store.BrowserCallbacksById.Values);
        Assert.Equal("ins-local-callback", callback.InstallationId);
        Assert.Equal(InstallBrowserCallbackStates.Pending, callback.Status);
    }

    [Fact]
    public async Task Browser_install_link_matches_linux_callback_platform_to_rid_backed_manifest_artifact()
    {
        using Fixture fixture = new(authenticated: true);
        fixture.Controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };
        fixture.Controller.ControllerContext.HttpContext.Request.Path = "/account/access/install-link";
        fixture.Controller.ControllerContext.HttpContext.Request.Headers.Authorization = "Bearer desktop-access-token";

        IActionResult result = await fixture.Controller.BrowserInstallLink(
            installationId: "ins-linux-route",
            headId: "avalonia",
            applicationVersion: "6.0.1-preview",
            releaseChannel: "preview",
            platform: "linux",
            arch: "x64",
            installLinkCallbackUri: "chummer://install-link",
            cancellationToken: CancellationToken.None);

        ContentResult page = Assert.IsType<ContentResult>(result);
        Assert.Contains("installationId=ins-linux-route", page.Content, StringComparison.Ordinal);

        InstallBrowserCallbackDto callback = Assert.Single(fixture.Store.BrowserCallbacksById.Values);
        Assert.Equal("avalonia-linux-x64-installer", callback.ArtifactId);
        Assert.Equal(InstallBrowserCallbackStates.Pending, callback.Status);
    }

    [Fact]
    public async Task Browser_install_link_matches_windows_callback_platform_to_rid_backed_manifest_artifact()
    {
        using Fixture fixture = new(authenticated: true);
        fixture.Controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };
        fixture.Controller.ControllerContext.HttpContext.Request.Path = "/account/access/install-link";
        fixture.Controller.ControllerContext.HttpContext.Request.Headers.Authorization = "Bearer desktop-access-token";

        IActionResult result = await fixture.Controller.BrowserInstallLink(
            installationId: "ins-windows-rid-route",
            headId: "avalonia",
            applicationVersion: "6.0.1-preview",
            releaseChannel: "preview",
            platform: "windows",
            arch: "x64",
            installLinkCallbackUri: "chummer://install-link",
            cancellationToken: CancellationToken.None);

        ContentResult page = Assert.IsType<ContentResult>(result);
        Assert.Contains("installationId=ins-windows-rid-route", page.Content, StringComparison.Ordinal);

        InstallBrowserCallbackDto callback = Assert.Single(fixture.Store.BrowserCallbacksById.Values);
        Assert.Equal("avalonia-win-x64-installer", callback.ArtifactId);
        Assert.Equal(InstallBrowserCallbackStates.Pending, callback.Status);
    }

    [Fact]
    public async Task Browser_install_link_preserves_only_bounded_state_from_app_local_callback()
    {
        using Fixture fixture = new(authenticated: true);
        fixture.Controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };
        fixture.Controller.ControllerContext.HttpContext.Request.Path = "/account/access/install-link";
        fixture.Controller.ControllerContext.HttpContext.Request.Headers.Authorization = "Bearer desktop-access-token";

        IActionResult result = await fixture.Controller.BrowserInstallLink(
            installationId: "ins-authoritative",
            headId: "avalonia",
            applicationVersion: "6.0.1-preview",
            releaseChannel: "preview",
            platform: "windows",
            arch: "x64",
            installLinkCallbackUri: "http://127.0.0.1:47761/install-link/callback?state=desktop&accessToken=stale-access&grantId=stale-grant&claimCode=stale-claim&claimTicketId=stale-ticket&ticketId=stale-ticket-id&receiptId=stale-receipt&installedBuildReceiptId=stale-installed-receipt&callbackCode=stale-callback&code=stale-code&unknown=unknown-query-secret#state=desktop-fragment&nonce=fragment-proof&accessToken=fragment-access&unknown=unknown-fragment-secret",
            cancellationToken: CancellationToken.None);

        ContentResult page = Assert.IsType<ContentResult>(result);
        Assert.True(TryExtractPrimaryHref(page.Content!, out string callbackHref), "The controller should render a manual callback link.");
        string decodedCallbackHref = WebUtility.HtmlDecode(callbackHref);
        Assert.Contains("state=desktop", decodedCallbackHref, StringComparison.Ordinal);
        Assert.Contains("#state=desktop-fragment", decodedCallbackHref, StringComparison.Ordinal);
        Assert.Contains("nonce=fragment-proof", decodedCallbackHref, StringComparison.Ordinal);
        Assert.Contains("code=", decodedCallbackHref, StringComparison.Ordinal);
        Assert.Contains("installationId=ins-authoritative", decodedCallbackHref, StringComparison.Ordinal);
        Assert.DoesNotContain("stale-access", decodedCallbackHref, StringComparison.Ordinal);
        Assert.DoesNotContain("stale-grant", decodedCallbackHref, StringComparison.Ordinal);
        Assert.DoesNotContain("stale-claim", decodedCallbackHref, StringComparison.Ordinal);
        Assert.DoesNotContain("stale-ticket", decodedCallbackHref, StringComparison.Ordinal);
        Assert.DoesNotContain("stale-ticket-id", decodedCallbackHref, StringComparison.Ordinal);
        Assert.DoesNotContain("stale-receipt", decodedCallbackHref, StringComparison.Ordinal);
        Assert.DoesNotContain("stale-installed-receipt", decodedCallbackHref, StringComparison.Ordinal);
        Assert.DoesNotContain("stale-callback", decodedCallbackHref, StringComparison.Ordinal);
        Assert.DoesNotContain("stale-code", decodedCallbackHref, StringComparison.Ordinal);
        Assert.DoesNotContain("fragment-access", decodedCallbackHref, StringComparison.Ordinal);
        Assert.DoesNotContain("unknown-query-secret", decodedCallbackHref, StringComparison.Ordinal);
        Assert.DoesNotContain("unknown-fragment-secret", decodedCallbackHref, StringComparison.Ordinal);
        Assert.Contains("installLinkTransport=grant_callback", decodedCallbackHref, StringComparison.Ordinal);
    }

    [Fact]
    public async Task Browser_install_link_renders_visible_recovery_page_when_artifact_is_missing()
    {
        using Fixture fixture = new(authenticated: true);
        fixture.Controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };
        fixture.Controller.ControllerContext.HttpContext.Request.Path = "/account/access/install-link";
        fixture.Controller.ControllerContext.HttpContext.Request.Headers.Authorization = "Bearer desktop-access-token";

        IActionResult result = await fixture.Controller.BrowserInstallLink(
            installationId: "ins-missing-artifact",
            headId: "unknown-head",
            applicationVersion: "run-20260612-121055",
            releaseChannel: "docker",
            platform: "windows",
            arch: "x64",
            installLinkCallbackUri: "chummer://install-link",
            cancellationToken: CancellationToken.None);

        ContentResult page = Assert.IsType<ContentResult>(result);
        Assert.Equal(StatusCodes.Status404NotFound, page.StatusCode);
        Assert.Contains("This install needs a current desktop package", page.Content, StringComparison.Ordinal);
        Assert.Contains("could not match this copy to a current desktop installer", page.Content, StringComparison.Ordinal);
        Assert.Contains("Open downloads", page.Content, StringComparison.Ordinal);
        Assert.Contains("ins-missing-artifact", page.Content, StringComparison.Ordinal);
        Assert.DoesNotContain("published desktop artifact", page.Content, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("app handoff", page.Content, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void Desktop_launch_exchange_accepts_valid_ticket_for_matching_claimed_install()
    {
        using Fixture fixture = new(authenticated: true);
        InstallationGrantDto grant = fixture.SeedClaimedInstall("ins-launch-valid", fixture.User.UserId, fixture.SubjectId);
        AccountDesktopLaunchTicketIssueResult issued = fixture.DesktopLaunchTickets.Issue("character", "dossier-7", fixture.User.UserId, fixture.SubjectId);

        ActionResult<DesktopAccountLaunchExchangeResponseDto> result = fixture.Controller.ExchangeDesktopLaunch(
            new DesktopAccountLaunchExchangeRequestDto(
                InstallationId: "ins-launch-valid",
                AccessToken: grant.AccessToken,
                Ticket: issued.Ticket));

        OkObjectResult ok = Assert.IsType<OkObjectResult>(result.Result);
        DesktopAccountLaunchExchangeResponseDto payload = Assert.IsType<DesktopAccountLaunchExchangeResponseDto>(ok.Value);
        Assert.Equal("character", payload.Kind);
        Assert.Equal("dossier-7", payload.ResourceId);
    }

    [Fact]
    public void Desktop_launch_exchange_rejects_ticket_for_another_identity()
    {
        using Fixture fixture = new(authenticated: true);
        InstallationGrantDto grant = fixture.SeedClaimedInstall("ins-launch-mismatch", fixture.User.UserId, fixture.SubjectId);
        AccountDesktopLaunchTicketIssueResult issued = fixture.DesktopLaunchTickets.Issue("group", "group-4", userId: "someone-else", subjectId: "subject.someone-else");

        ActionResult<DesktopAccountLaunchExchangeResponseDto> result = fixture.Controller.ExchangeDesktopLaunch(
            new DesktopAccountLaunchExchangeRequestDto(
                InstallationId: "ins-launch-mismatch",
                AccessToken: grant.AccessToken,
                Ticket: issued.Ticket));

        ObjectResult problem = Assert.IsType<ObjectResult>(result.Result);
        Assert.Equal(StatusCodes.Status403Forbidden, problem.StatusCode);
        ProblemDetails details = Assert.IsType<ProblemDetails>(problem.Value);
        Assert.Equal("desktop launch ticket does not belong to this linked install.", details.Detail);
    }

    [Fact]
    public void Desktop_launch_exchange_rejects_invalid_ticket()
    {
        using Fixture fixture = new(authenticated: true);
        InstallationGrantDto grant = fixture.SeedClaimedInstall("ins-launch-invalid", fixture.User.UserId, fixture.SubjectId);

        ActionResult<DesktopAccountLaunchExchangeResponseDto> result = fixture.Controller.ExchangeDesktopLaunch(
            new DesktopAccountLaunchExchangeRequestDto(
                InstallationId: "ins-launch-invalid",
                AccessToken: grant.AccessToken,
                Ticket: "not-a-real-ticket"));

        ObjectResult problem = Assert.IsType<ObjectResult>(result.Result);
        Assert.Equal(StatusCodes.Status400BadRequest, problem.StatusCode);
        ProblemDetails details = Assert.IsType<ProblemDetails>(problem.Value);
        Assert.Equal("desktop launch ticket is invalid.", details.Detail);
    }

    private static bool TryExtractPrimaryHref(string content, out string href)
    {
        const string classMarker = "class=\"button-like button-like--primary\"";
        int anchorStart = content.IndexOf(classMarker, StringComparison.Ordinal);
        if (anchorStart < 0)
        {
            href = string.Empty;
            return false;
        }

        int hrefMarker = content.IndexOf("href=\"", anchorStart, StringComparison.Ordinal);
        if (hrefMarker < 0)
        {
            href = string.Empty;
            return false;
        }

        int start = hrefMarker + "href=\"".Length;
        int end = content.IndexOf('"', start);
        if (end < 0)
        {
            href = string.Empty;
            return false;
        }

        href = content[start..end];
        return true;
    }

    private static void AssertSensitiveResponseHeaders(IHeaderDictionary headers)
    {
        Assert.Equal("private, no-store, max-age=0", headers.CacheControl.ToString());
        Assert.Equal("no-store, max-age=0", headers["CDN-Cache-Control"].ToString());
        Assert.Equal("no-store, max-age=0", headers["Cloudflare-CDN-Cache-Control"].ToString());
        Assert.Equal("no-store", headers["Surrogate-Control"].ToString());
        Assert.Equal("no-cache", headers.Pragma.ToString());
        Assert.Equal("0", headers.Expires.ToString());
        Assert.Equal("no-referrer", headers["Referrer-Policy"].ToString());
    }

    private sealed class Fixture : IDisposable
    {
        private readonly string _root;

        public Fixture(bool authenticated)
        {
            _root = Path.Combine(Path.GetTempPath(), "chummer-install-link-controller-tests", Guid.NewGuid().ToString("N"));
            string downloadsRoot = Path.Combine(_root, "downloads");
            Directory.CreateDirectory(downloadsRoot);
            File.WriteAllText(
                Path.Combine(downloadsRoot, "releases.json"),
                """
                {
                  "version": "6.0.1-preview",
                  "channel": "preview",
                  "publishedAt": "2026-04-15T08:00:00Z",
                  "downloads": [
                    {
                      "id": "avalonia-linux-x64-installer",
                      "platform": "Avalonia Desktop Linux x64 Installer",
                      "url": "/downloads/files/chummer-avalonia-linux-x64-installer.deb",
                      "sha256": "c3",
                      "sizeBytes": 303,
                      "head": "avalonia",
                      "platformId": "linux-x64",
                      "arch": "x64",
                      "kind": "installer",
                      "fileName": "chummer-avalonia-linux-x64-installer.deb",
                      "installAccessClass": "open_public"
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
                      "platformId": "windows",
                      "arch": "x64",
                      "kind": "installer",
                      "fileName": "chummer-blazor-desktop-win-x64-installer.exe",
                      "installAccessClass": "account_required"
                    }
                  ]
                }
                """);

            IConfiguration configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_DOWNLOADS_SOURCE_ROOT"] = downloadsRoot,
                    ["CHUMMER_INSTALL_LINKING_STORE_PATH"] = Path.Combine(_root, "install-linking-store.json"),
                    ["CHUMMER_INSTALL_BROWSER_CALLBACK_LIFETIME_MINUTES"] = "15",
                    ["CHUMMER_COMMUNITY_STORE_PATH"] = Path.Combine(_root, "community-store.json"),
                    ["IDENTITY_SERVICE_BASE_URL"] = "http://identity.example"
                })
                .Build();

            HubIdentityClient identity = new(
                new HttpClient(new IdentityHandler(authenticated))
                {
                    BaseAddress = new Uri("http://identity.example")
                },
                configuration,
                NullLogger<HubIdentityClient>.Instance);
            CommunityStore communityStore = new(configuration, NullLogger<CommunityStore>.Instance);
            AccountService accounts = new(communityStore);
            IDataProtectionProvider dataProtection = DataProtectionProvider.Create(new DirectoryInfo(Path.Combine(_root, "keys")));
            InstallLinkingStore installLinkingStore = new(
                configuration,
                dataProtection,
                NullLogger<InstallLinkingStore>.Instance);
            AccountDesktopLaunchTicketService desktopLaunchTickets = new(dataProtection, configuration);

            Identity = identity;
            Accounts = accounts;
            Store = installLinkingStore;
            InstallLinking = new InstallLinkingService(installLinkingStore, configuration);
            Releases = new PublicReleaseManifestService(configuration);
            DesktopLaunchTickets = desktopLaunchTickets;
            Controller = new InstallLinkingController(
                identity,
                accounts,
                InstallLinking,
                desktopLaunchTickets,
                Releases,
                supportCases: null!,
                supportPresentation: new SupportCasePresentationService(),
                configuration);

            if (authenticated)
            {
                User = accounts.EnsureUser(SubjectId, "Archon", "archon@example.com");
            }
        }

        public string SubjectId { get; } = "subject.install.browser";

        public HubIdentityClient Identity { get; }

        public AccountService Accounts { get; }

        public InstallLinkingStore Store { get; }

        public InstallLinkingService InstallLinking { get; }

        public PublicReleaseManifestService Releases { get; }

        public AccountDesktopLaunchTicketService DesktopLaunchTickets { get; }

        public InstallLinkingController Controller { get; }

        public Chummer.Run.Contracts.Community.HubUserDto User { get; private set; } = null!;

        public InstallationGrantDto SeedClaimedInstall(string installationId, string userId, string? subjectId)
        {
            lock (Store.Gate)
            {
                DateTimeOffset now = DateTimeOffset.UtcNow;
                InstallationGrantDto grant = new(
                    GrantId: $"grant-{installationId}",
                    InstallationId: installationId,
                    Status: InstallationGrantStates.Active,
                    AccessToken: $"access-{installationId}",
                    IssuedAtUtc: now.AddMinutes(-5),
                    ExpiresAtUtc: now.AddHours(8),
                    UserId: userId,
                    SubjectId: subjectId);
                ClaimedInstallationDto installation = new(
                    InstallationId: installationId,
                    ArtifactId: "avalonia-win-x64-installer",
                    Channel: "preview",
                    Version: "6.0.1-preview",
                    InstallAccessClass: InstallAccessClasses.AccountRequired,
                    Status: ClaimedInstallationStates.Active,
                    CreatedAtUtc: now.AddHours(-1),
                    UpdatedAtUtc: now,
                    UserId: userId,
                    SubjectId: subjectId,
                    PublicKey: "public-key",
                    ClaimTicketId: $"ticket-{installationId}",
                    HeadId: "avalonia",
                    Platform: "windows",
                    Arch: "x64",
                    HostLabel: "Test host",
                    GrantId: grant.GrantId);
                Store.InstallationsById[installationId] = installation;
                Store.GrantsById[grant.GrantId] = grant;
                Store.PersistLocked();
                return grant;
            }
        }

        public void Dispose()
        {
            if (Directory.Exists(_root))
            {
                Directory.Delete(_root, recursive: true);
            }
        }
    }

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
                    SessionId: "session-123",
                    SubjectId: "subject.install.browser",
                    Roles: ["user"],
                    ExpiresAtUtc: DateTimeOffset.UtcNow.AddHours(1))));
            }

            if (request.RequestUri?.AbsolutePath.EndsWith("/api/v1/identity/subjects/subject.install.browser", StringComparison.Ordinal) == true)
            {
                return Task.FromResult(JsonResponse(new IdentitySubjectResponse(
                    SubjectId: "subject.install.browser",
                    DisplayName: "Archon",
                    Email: "archon@example.com",
                    Roles: ["user"],
                    UpdatedAtUtc: DateTimeOffset.UtcNow)));
            }

            return Task.FromResult(new HttpResponseMessage(HttpStatusCode.NotFound));
        }

        private static HttpResponseMessage JsonResponse<T>(T payload)
            => new(HttpStatusCode.OK)
            {
                Content = new StringContent(JsonSerializer.Serialize(payload), Encoding.UTF8, "application/json")
            };
    }
}
