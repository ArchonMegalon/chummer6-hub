using Chummer.Run.Api.Services;
using Chummer.Run.Api.Controllers;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Configuration;
using Xunit;

namespace Chummer.Tests;

public sealed class PublicPlaySessionAccessPolicyTests
{
    [Theory]
    [InlineData("/mobile")]
    [InlineData("/mobile/player")]
    [InlineData("/mobile/gm")]
    [InlineData("/mobile/observer")]
    [InlineData("/mobile/service-worker.js")]
    public void QueryFreeGetInstallRoutesRemainPublic(string path)
    {
        var context = CreateContext(path);

        Assert.True(PublicPlaySessionAccessPolicy.IsPublicQueryFreeInstallRequest(context.Request));
        Assert.False(PublicPlaySessionAccessPolicy.RequiresSessionGrant(context.Request));
    }

    [Theory]
    [InlineData("/mobile?sessionId=forged")]
    [InlineData("/mobile/gm?role=GameMaster")]
    [InlineData("/mobile/player?deviceId=forged")]
    [InlineData("/_blazor")]
    [InlineData("/_blazor/negotiate")]
    [InlineData("/api/play")]
    [InlineData("/api/play/turn-companion/forged")]
    public void LiveAndSessionBearingRoutesRequireGrant(string target)
    {
        var context = CreateContext(target);

        Assert.True(PublicPlaySessionAccessPolicy.RequiresSessionGrant(context.Request));
    }

    [Fact]
    public async Task DefaultOffFeatureDeniesWithoutResolvingIdentity()
    {
        var identity = new RecordingIdentityResolver();
        var grants = new RecordingGrantAuthorizer(allowed: true);
        var policy = CreatePolicy(enabled: false, identity, grants);

        bool allowed = await policy.HasAccessAsync(
            CreateContext("/api/play/turn-companion/forged"),
            CancellationToken.None);

        Assert.False(allowed);
        Assert.Equal(0, identity.CallCount);
        Assert.Equal(0, grants.CallCount);
    }

    [Fact]
    public async Task AuthenticatedSubjectWithoutServerGrantIsDenied()
    {
        var identity = new RecordingIdentityResolver();
        var grants = new RecordingGrantAuthorizer(allowed: false);
        var policy = CreatePolicy(enabled: true, identity, grants);
        DefaultHttpContext context = CreateContext("/api/play/turn-companion/forged?role=GameMaster");

        bool allowed = await policy.HasAccessAsync(context, CancellationToken.None);

        Assert.False(allowed);
        Assert.Equal(1, identity.CallCount);
        Assert.Equal(1, grants.CallCount);
        Assert.Equal("subject.test", grants.LastRequest?.SubjectId);
        Assert.Equal("forged", grants.LastRequest?.SessionId);
        Assert.Equal(PublicPlayPrivateRouteKind.TurnCompanion, grants.LastRequest?.RouteKind);
    }

    [Fact]
    public async Task ProductionGrantImplementationMustExplicitlyApproveTheAuthenticatedSubject()
    {
        var identity = new RecordingIdentityResolver();
        var grants = new RecordingGrantAuthorizer(allowed: true);
        var policy = CreatePolicy(enabled: true, identity, grants);

        bool allowed = await policy.HasAccessAsync(
            CreateContext("/api/play/turn-companion/granted"),
            CancellationToken.None);

        Assert.True(allowed);
        Assert.Equal("granted", grants.LastRequest?.SessionId);
    }

    [Fact]
    public async Task QueueStatusUsesTheTypedSessionSegmentInsteadOfTheFinalPathSegment()
    {
        var identity = new RecordingIdentityResolver();
        var grants = new RecordingGrantAuthorizer(allowed: false);
        var policy = CreatePolicy(enabled: true, identity, grants);

        bool allowed = await policy.HasAccessAsync(
            CreateContext("/api/play/turn-companion/session-alpha/queue-status?sessionId=session-alpha"),
            CancellationToken.None);

        Assert.False(allowed);
        Assert.Equal("session-alpha", grants.LastRequest?.SessionId);
        Assert.Equal(PublicPlayPrivateRouteKind.TurnCompanionQueueStatus, grants.LastRequest?.RouteKind);
    }

    [Theory]
    [InlineData("/api/play/turn-companion/path-session/queue-status?sessionId=query-session")]
    [InlineData("/api/play/turn-companion/path%2Fescape/queue-status")]
    [InlineData("/api/play/turn-companion/../queue-status")]
    [InlineData("/api/play/turn-companion/session-alpha?sessionId=one&sessionId=two")]
    [InlineData("/api/play/quick-action")]
    [InlineData("/api/play/turn-companion/session-alpha/unknown")]
    [InlineData("/api/play/turn-companion/session-alpha?extra=one")]
    [InlineData("/api/play/turn-companion/session-alpha?role=gm")]
    [InlineData("/_blazor/negotiate")]
    [InlineData("/mobile/gm?sessionId=session-alpha")]
    public async Task MismatchedOrAmbiguousSessionRoutesFailBeforeIdentityOrGrantLookup(string target)
    {
        var identity = new RecordingIdentityResolver();
        var grants = new RecordingGrantAuthorizer(allowed: true);
        var policy = CreatePolicy(enabled: true, identity, grants);

        bool allowed = await policy.HasAccessAsync(CreateContext(target), CancellationToken.None);

        Assert.False(allowed);
        Assert.Equal(0, identity.CallCount);
        Assert.Equal(0, grants.CallCount);
    }

    [Theory]
    [InlineData("/api/play/turn-companion/session-alpha/replay", "GET")]
    [InlineData("/api/play/turn-companion/session-alpha/queue-status", "POST")]
    [InlineData("/api/play/turn-companion/session-alpha/acknowledge", "HEAD")]
    public async Task MethodMismatchFailsBeforeIdentityOrGrantLookup(string target, string method)
    {
        var identity = new RecordingIdentityResolver();
        var grants = new RecordingGrantAuthorizer(allowed: true);
        var policy = CreatePolicy(enabled: true, identity, grants);

        bool allowed = await policy.HasAccessAsync(CreateContext(target, method), CancellationToken.None);

        Assert.False(allowed);
        Assert.Equal(0, identity.CallCount);
        Assert.Equal(0, grants.CallCount);
    }

    [Theory]
    [InlineData("/api/play/turn-companion/session-alpha", "GET", PublicPlayPrivateRouteKind.TurnCompanion)]
    [InlineData("/api/play/turn-companion/session-alpha/queue-status", "HEAD", PublicPlayPrivateRouteKind.TurnCompanionQueueStatus)]
    [InlineData("/api/play/turn-companion/session-alpha/replay", "POST", PublicPlayPrivateRouteKind.TurnCompanionCommand)]
    [InlineData("/api/play/turn-companion/session-alpha/acknowledge", "POST", PublicPlayPrivateRouteKind.TurnCompanionCommand)]
    public void ExactFutureRoutesResolveToTypedKinds(
        string target,
        string method,
        PublicPlayPrivateRouteKind expectedKind)
    {
        DefaultHttpContext context = CreateContext(target, method);

        Assert.True(PublicPlaySessionAccessPolicy.TryResolvePrivateRoute(context.Request, out var route));
        Assert.NotNull(route);
        Assert.Equal(expectedKind, route.Kind);
        Assert.Equal("session-alpha", route.SessionId);
    }

    [Theory]
    [InlineData("api")]
    [InlineData("blazor")]
    public async Task LegacyPrivateRoutesRemainDenyAllEvenIfAPlaceholderPolicyWouldAllow(string route)
    {
        var controller = new LegacySurfaceRedirectController(
            playSessionAccess: new AllowingAccessPolicy())
        {
            ControllerContext = new ControllerContext
            {
                HttpContext = new DefaultHttpContext()
            }
        };
        controller.HttpContext.Response.Body = new MemoryStream();
        controller.HttpContext.Request.Method = HttpMethods.Get;
        controller.HttpContext.Request.Path = route == "api"
            ? "/api/play/turn-companion/forged"
            : "/_blazor/negotiate";

        IActionResult result = route == "api"
            ? await controller.PlayApi("turn-companion/forged", CancellationToken.None)
            : await controller.PlayBlazorCircuit("negotiate", CancellationToken.None);

        Assert.IsType<EmptyResult>(result);
        Assert.Equal(StatusCodes.Status404NotFound, controller.Response.StatusCode);
    }

    private static PublicPlaySessionAccessPolicy CreatePolicy(
        bool enabled,
        IPublicPlayIdentityResolver identity,
        IPlaySessionGrantAuthorizer grants)
    {
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                [PublicPlaySessionAccessPolicy.LiveSessionProxyFeature] = enabled.ToString()
            })
            .Build();
        return new PublicPlaySessionAccessPolicy(configuration, identity, grants);
    }

    private static DefaultHttpContext CreateContext(string target, string method = "GET")
    {
        var context = new DefaultHttpContext();
        context.Request.Method = method;
        int queryIndex = target.IndexOf('?', StringComparison.Ordinal);
        context.Request.Path = queryIndex < 0 ? target : target[..queryIndex];
        context.Request.QueryString = queryIndex < 0
            ? QueryString.Empty
            : new QueryString(target[queryIndex..]);
        return context;
    }

    private sealed class RecordingIdentityResolver : IPublicPlayIdentityResolver
    {
        public int CallCount { get; private set; }

        public Task<AuthenticatedHubSubject> RequireSubjectAsync(
            HttpRequest request,
            CancellationToken cancellationToken)
        {
            CallCount++;
            return Task.FromResult(new AuthenticatedHubSubject(
                "subject.test",
                "Test Runner",
                "runner@example.invalid",
                ["player"],
                "test-access-token"));
        }
    }

    private sealed class RecordingGrantAuthorizer(bool allowed) : IPlaySessionGrantAuthorizer
    {
        public int CallCount { get; private set; }

        public PublicPlaySessionGrantRequest? LastRequest { get; private set; }

        public Task<bool> HasGrantAsync(
            PublicPlaySessionGrantRequest request,
            CancellationToken cancellationToken)
        {
            CallCount++;
            LastRequest = request;
            return Task.FromResult(allowed);
        }
    }

    private sealed class AllowingAccessPolicy : IPublicPlaySessionAccessPolicy
    {
        public Task<bool> HasAccessAsync(HttpContext context, CancellationToken cancellationToken)
            => Task.FromResult(true);
    }

}
