using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using Chummer.Run.Api.Controllers;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Contracts.Community;
using Chummer.Run.Contracts.Identity;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class AccountLinksControllerSecurityTests
{
    [Fact]
    public void InlinePreviewLinkRequiresLoopbackInsteadOfTrustingRemoteEqualsLocal()
    {
        DefaultHttpContext httpContext = new();
        httpContext.Request.Host = new HostString("chummer.run");
        httpContext.Connection.RemoteIpAddress = IPAddress.Parse("10.0.0.5");
        httpContext.Connection.LocalIpAddress = IPAddress.Parse("10.0.0.5");

        Assert.False(HubBrowserAuthService.ShouldExposeInlinePreviewLink(httpContext.Request));
    }

    [Fact]
    public void InlinePreviewLinkStillAllowsLocalDevelopmentLoopbackRequests()
    {
        DefaultHttpContext httpContext = new();
        httpContext.Request.Host = new HostString("localhost");
        httpContext.Connection.RemoteIpAddress = IPAddress.Loopback;
        httpContext.Connection.LocalIpAddress = IPAddress.Loopback;

        Assert.True(HubBrowserAuthService.ShouldExposeInlinePreviewLink(httpContext.Request));
    }

    [Fact]
    public async Task RecoveryEmailStartDoesNotExposePreviewTicketToRemoteBrowsers()
    {
        const string rawTicket = "eml_remote_preview_secret";
        string storePath = Path.Combine(Path.GetTempPath(), "chummer-account-links-tests", $"{Guid.NewGuid():N}.json");
        Directory.CreateDirectory(Path.GetDirectoryName(storePath)!);
        try
        {
            IConfiguration configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_COMMUNITY_STORE_PATH"] = storePath,
                    ["IDENTITY_SERVICE_BASE_URL"] = "https://identity.example.test",
                    ["IDENTITY_EMAIL_START_ENABLED"] = "true"
                })
                .Build();
            var store = new CommunityStore(configuration, NullLogger<CommunityStore>.Instance);
            var accounts = new AccountService(store);
            var links = new IdentityLinkService(store, accounts, configuration);
            var identity = new HubIdentityClient(
                new HttpClient(new IdentityHandler()),
                configuration,
                NullLogger<HubIdentityClient>.Instance);
            var browserAuth = new HubBrowserAuthService(
                new HttpClient(new BrowserAuthHandler(rawTicket)),
                configuration,
                NullLogger<HubBrowserAuthService>.Instance);
            var controller = new AccountLinksController(
                links,
                channelMessaging: null!,
                identity,
                accounts,
                browserAuth,
                new HubEmailLinkVerificationService(DataProtectionProvider.Create("account-links-security-test")))
            {
                ControllerContext = new ControllerContext
                {
                    HttpContext = new DefaultHttpContext()
                }
            };
            HttpContext httpContext = controller.ControllerContext.HttpContext;
            httpContext.Request.Scheme = "https";
            httpContext.Request.Host = new HostString("chummer.run");
            httpContext.Connection.RemoteIpAddress = IPAddress.Parse("203.0.113.10");
            httpContext.Connection.LocalIpAddress = IPAddress.Parse("10.0.0.5");
            httpContext.Request.Headers.Authorization = "Bearer remote-browser-token";
            httpContext.RequestServices = new ServiceCollection()
                .AddSingleton(configuration)
                .BuildServiceProvider();

            ActionResult<RecoveryEmailLinkStartResponse> result = await controller.StartRecoveryEmailLink(
                new StartRecoveryEmailLinkRequest(
                    SubjectId: "subject.demo",
                    Email: "recovery@example.invalid",
                    NextPath: "/account"),
                CancellationToken.None);

            var ok = Assert.IsType<OkObjectResult>(result.Result);
            var payload = Assert.IsType<RecoveryEmailLinkStartResponse>(ok.Value);
            Assert.Equal("preview_inline_link", payload.DeliveryMode);
            Assert.Null(payload.PreviewHref);
            string serializedPayload = JsonSerializer.Serialize(payload);
            Assert.DoesNotContain(rawTicket, serializedPayload, StringComparison.Ordinal);
        }
        finally
        {
            if (File.Exists(storePath))
            {
                File.Delete(storePath);
            }
        }
    }

    [Fact]
    public async Task RecoveryEmailStartFailsClosedWhenEmailSignInIsPaused()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), "chummer-account-links-tests", Guid.NewGuid().ToString("N"));
        string storePath = Path.Combine(tempRoot, "community.json");
        string pauseFlagPath = Path.Combine(tempRoot, "auth_signin_automation_paused.flag");
        Directory.CreateDirectory(tempRoot);
        File.WriteAllText(pauseFlagPath, "paused by user request");

        try
        {
            IConfiguration configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_COMMUNITY_STORE_PATH"] = storePath,
                    ["IDENTITY_SERVICE_BASE_URL"] = "https://identity.example.test",
                    ["IDENTITY_EMAIL_START_ENABLED"] = "true",
                    ["CHUMMER_AUTH_SIGNIN_AUTOMATION_PAUSE_FLAG"] = pauseFlagPath
                })
                .Build();
            var store = new CommunityStore(configuration, NullLogger<CommunityStore>.Instance);
            var accounts = new AccountService(store);
            var links = new IdentityLinkService(store, accounts, configuration);
            var identity = new HubIdentityClient(
                new HttpClient(new IdentityHandler()),
                configuration,
                NullLogger<HubIdentityClient>.Instance);
            var browserHandler = new BrowserAuthHandler("eml_should_not_send");
            var browserAuth = new HubBrowserAuthService(
                new HttpClient(browserHandler),
                configuration,
                NullLogger<HubBrowserAuthService>.Instance);
            var controller = new AccountLinksController(
                links,
                channelMessaging: null!,
                identity,
                accounts,
                browserAuth,
                new HubEmailLinkVerificationService(DataProtectionProvider.Create("account-links-security-test")))
            {
                ControllerContext = new ControllerContext
                {
                    HttpContext = new DefaultHttpContext()
                }
            };
            HttpContext httpContext = controller.ControllerContext.HttpContext;
            httpContext.Request.Headers.Authorization = "Bearer remote-browser-token";
            httpContext.RequestServices = new ServiceCollection()
                .AddControllers()
                .Services
                .AddSingleton(configuration)
                .BuildServiceProvider();

            ActionResult<RecoveryEmailLinkStartResponse> result = await controller.StartRecoveryEmailLink(
                new StartRecoveryEmailLinkRequest(
                    SubjectId: "subject.demo",
                    Email: "recovery@example.invalid",
                    NextPath: "/account"),
                CancellationToken.None);

            ObjectResult unavailable = Assert.IsType<ObjectResult>(result.Result);
            Assert.Equal(StatusCodes.Status503ServiceUnavailable, unavailable.StatusCode);
            ProblemDetails details = Assert.IsType<ProblemDetails>(unavailable.Value);
            Assert.Contains("paused", details.Detail, StringComparison.OrdinalIgnoreCase);
            Assert.False(browserHandler.Called);
        }
        finally
        {
            if (Directory.Exists(tempRoot))
            {
                Directory.Delete(tempRoot, recursive: true);
            }
        }
    }

    private sealed class IdentityHandler : HttpMessageHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            if (request.RequestUri?.AbsolutePath.EndsWith("/api/v1/identity/introspect", StringComparison.Ordinal) == true)
            {
                return Task.FromResult(JsonResponse(new IdentityIntrospectionResponse(
                    Active: true,
                    SessionId: "session.demo",
                    SubjectId: "subject.demo",
                    Roles: ["player"],
                    ExpiresAtUtc: DateTimeOffset.UtcNow.AddHours(1))));
            }

            if (request.RequestUri?.AbsolutePath.EndsWith("/api/v1/identity/subjects/subject.demo", StringComparison.Ordinal) == true)
            {
                return Task.FromResult(JsonResponse(new IdentitySubjectResponse(
                    SubjectId: "subject.demo",
                    DisplayName: "Runner Demo",
                    Email: "runner@example.invalid",
                    Roles: ["player"],
                    UpdatedAtUtc: DateTimeOffset.UtcNow)));
            }

            return Task.FromResult(new HttpResponseMessage(HttpStatusCode.NotFound));
        }
    }

    private sealed class BrowserAuthHandler(string rawTicket) : HttpMessageHandler
    {
        public bool Called { get; private set; }

        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            Called = true;
            return Task.FromResult(JsonResponse(new EmailAuthStartResponse(
                TicketId: rawTicket,
                SubjectId: "subject.demo",
                Email: "recovery@example.invalid",
                DisplayName: "Runner Demo",
                NextPath: "/auth/email/link/callback?token=verification-token",
                CreatedAtUtc: DateTimeOffset.UtcNow,
                ExpiresAtUtc: DateTimeOffset.UtcNow.AddMinutes(15),
                DeliveryMode: "preview_inline_link",
                PreviewNote: "Development preview callback link.")));
        }
    }

    private static HttpResponseMessage JsonResponse<T>(T payload)
        => new(HttpStatusCode.OK)
        {
            Content = JsonContent.Create(payload)
        };
}
