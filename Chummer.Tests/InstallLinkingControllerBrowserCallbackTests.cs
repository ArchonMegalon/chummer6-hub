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
        Assert.StartsWith("/auth/google/start?next=", redirect.Url, StringComparison.Ordinal);
        Assert.Contains("%2Faccount%2Faccess%2Finstall-link%3FinstallationId%3Dins-unauth", redirect.Url, StringComparison.Ordinal);
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
    }

    [Fact]
    public async Task Browser_install_link_redirects_authenticated_requests_back_to_callback_with_code()
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

        RedirectResult redirect = Assert.IsType<RedirectResult>(result);
        Assert.True(Uri.TryCreate(redirect.Url, UriKind.Absolute, out Uri? callbackUri), "The controller should emit a valid callback URI.");
        Assert.Equal("chummer", callbackUri.Scheme);
        Assert.Equal("install-link", callbackUri.Host);
        Assert.Contains("code=", redirect.Url, StringComparison.Ordinal);
        Assert.Contains("installationId=ins-browser-route", redirect.Url, StringComparison.Ordinal);
        Assert.Contains("headId=avalonia", redirect.Url, StringComparison.Ordinal);
        Assert.Contains("installLinkMode=browser_callback", redirect.Url, StringComparison.Ordinal);
        Assert.Contains("installLinkTransport=grant_callback", redirect.Url, StringComparison.Ordinal);

        InstallBrowserCallbackDto callback = Assert.Single(fixture.Store.BrowserCallbacksById.Values);
        Assert.Equal("ins-browser-route", callback.InstallationId);
        Assert.Equal(InstallBrowserCallbackStates.Pending, callback.Status);
        Assert.Contains($"code={Uri.EscapeDataString(callback.CallbackCode)}", redirect.Url, StringComparison.Ordinal);
    }

    [Theory]
    [InlineData("http://127.0.0.1:47761/install-link/callback?state=desktop&nonce=callback-proof", "127.0.0.1", "/install-link/callback", true)]
    [InlineData("http://[::1]:47763/install-link/callback?state=desktop", "[::1]", "/install-link/callback", true)]
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

        RedirectResult redirect = Assert.IsType<RedirectResult>(result);
        Assert.True(Uri.TryCreate(redirect.Url, UriKind.Absolute, out Uri? redirectUri), "The controller should emit a valid app-local callback URI.");
        Assert.Equal(expectedHost, redirectUri.Host);
        Assert.Equal(expectedPath, redirectUri.AbsolutePath);
        Assert.Contains("code=", redirect.Url, StringComparison.Ordinal);
        if (expectDesktopState)
        {
            Assert.Contains("state=desktop", redirect.Url, StringComparison.Ordinal);
            if (callbackUri.Contains("nonce=callback-proof", StringComparison.Ordinal))
            {
                Assert.Contains("nonce=callback-proof", redirect.Url, StringComparison.Ordinal);
            }
        }

        Assert.Contains("installationId=ins-local-callback", redirect.Url, StringComparison.Ordinal);
        Assert.Contains("installLinkMode=browser_callback", redirect.Url, StringComparison.Ordinal);
        Assert.Contains("installLinkTransport=grant_callback", redirect.Url, StringComparison.Ordinal);

        InstallBrowserCallbackDto callback = Assert.Single(fixture.Store.BrowserCallbacksById.Values);
        Assert.Equal("ins-local-callback", callback.InstallationId);
        Assert.Equal(InstallBrowserCallbackStates.Pending, callback.Status);
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
                      "id": "avalonia-win-x64-installer",
                      "platform": "Avalonia Desktop Windows x64 Installer",
                      "url": "/downloads/files/chummer-avalonia-win-x64-installer.exe",
                      "sha256": "d4",
                      "sizeBytes": 404,
                      "head": "avalonia",
                      "platformId": "windows",
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
            InstallLinkingStore installLinkingStore = new(configuration, NullLogger<InstallLinkingStore>.Instance);

            Identity = identity;
            Accounts = accounts;
            Store = installLinkingStore;
            InstallLinking = new InstallLinkingService(installLinkingStore, configuration);
            Releases = new PublicReleaseManifestService(configuration);
            Controller = new InstallLinkingController(
                identity,
                accounts,
                InstallLinking,
                Releases,
                supportCases: null!,
                supportPresentation: new SupportCasePresentationService());

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

        public InstallLinkingController Controller { get; }

        public Chummer.Run.Contracts.Community.HubUserDto User { get; private set; } = null!;

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
