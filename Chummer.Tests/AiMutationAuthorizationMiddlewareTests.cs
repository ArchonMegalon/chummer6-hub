using System.Text.Json;
using Chummer.Run.AI.Security;
using Chummer.Run.AI.Services.Booster;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.Configuration;
using Xunit;

namespace Chummer.Tests;

public sealed class AiMutationAuthorizationMiddlewareTests
{
    [Theory]
    [InlineData("GET", AiPublicEndpoints.HealthPath)]
    [InlineData("HEAD", AiPublicEndpoints.HealthPath)]
    [InlineData("GET", AiPublicEndpoints.CapabilitiesPath)]
    [InlineData("HEAD", AiPublicEndpoints.CapabilitiesPath)]
    [InlineData("GET", "/api/health/")]
    public async Task AllowlistedOperationalRequestsRemainPublic(string method, string path)
    {
        bool nextCalled = false;
        var middleware = new AiMutationAuthorizationMiddleware(_ =>
        {
            nextCalled = true;
            return Task.CompletedTask;
        });
        DefaultHttpContext context = CreateContext(method, path);

        await middleware.InvokeAsync(context, BuildConfiguration());

        Assert.True(nextCalled);
        Assert.Equal(StatusCodes.Status200OK, context.Response.StatusCode);
    }

    [Fact]
    public async Task OptionsRequestsRemainPublicTransportPreflight()
    {
        bool nextCalled = false;
        var middleware = new AiMutationAuthorizationMiddleware(_ =>
        {
            nextCalled = true;
            return Task.CompletedTask;
        });
        DefaultHttpContext context = CreateContext("OPTIONS", "/api/v1/ai/conversations/private-session");

        await middleware.InvokeAsync(context, BuildConfiguration());

        Assert.True(nextCalled);
        Assert.Equal(StatusCodes.Status200OK, context.Response.StatusCode);
    }

    [Theory]
    [InlineData("/api/v1/ai/status")]
    [InlineData("/api/v1/ai/prompts")]
    [InlineData("/api/v1/ai/budget/private-session")]
    [InlineData("/api/v1/ai/skills/adapters")]
    [InlineData("/api/v1/ai/conversations/private-session")]
    [InlineData("/api/v1/ai/support/crashes/clusters")]
    [InlineData("/api/v1/ai/creative/assets")]
    [InlineData("/api/v1/ai/session/runtime-bundle/private-session/private-scene")]
    [InlineData("/api/v1/ai/spider/outbox/private-session/private-scene")]
    [InlineData("/api/v1/ai/gm-ops/private-session/private-scene")]
    [InlineData("/api/v1/ai/pipeline/projection")]
    [InlineData("/api/v1/ai/booster/leaderboard-projection")]
    [InlineData("/api/not-a-route")]
    public async Task SensitiveAndUnknownReadsFailClosedWhenNoTokenIsConfigured(string path)
    {
        bool nextCalled = false;
        var middleware = new AiMutationAuthorizationMiddleware(_ =>
        {
            nextCalled = true;
            return Task.CompletedTask;
        });
        DefaultHttpContext context = CreateContext("GET", path);

        await middleware.InvokeAsync(context, BuildConfiguration());

        Assert.False(nextCalled);
        Assert.Equal(StatusCodes.Status503ServiceUnavailable, context.Response.StatusCode);
    }

    [Fact]
    public async Task MutationFailsClosedWhenNoTokenIsConfigured()
    {
        bool nextCalled = false;
        var middleware = new AiMutationAuthorizationMiddleware(_ =>
        {
            nextCalled = true;
            return Task.CompletedTask;
        });
        DefaultHttpContext context = CreateContext("POST");

        await middleware.InvokeAsync(context, BuildConfiguration());

        Assert.False(nextCalled);
        Assert.Equal(StatusCodes.Status503ServiceUnavailable, context.Response.StatusCode);
        using JsonDocument problem = await ReadProblemAsync(context);
        Assert.Equal(StatusCodes.Status503ServiceUnavailable, problem.RootElement.GetProperty("status").GetInt32());
    }

    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData("Basic abc")]
    [InlineData("Bearer wrong-token")]
    public async Task MutationRejectsMissingOrInvalidBearerToken(string? authorization)
    {
        const string expectedToken = "expected-private-token";
        bool nextCalled = false;
        var middleware = new AiMutationAuthorizationMiddleware(_ =>
        {
            nextCalled = true;
            return Task.CompletedTask;
        });
        DefaultHttpContext context = CreateContext("PATCH");
        if (authorization is not null)
        {
            context.Request.Headers.Authorization = authorization;
        }

        await middleware.InvokeAsync(
            context,
            BuildConfiguration((AiMutationAuthorizationMiddleware.PrimaryTokenConfigurationKey, expectedToken)));

        Assert.False(nextCalled);
        Assert.Equal(StatusCodes.Status401Unauthorized, context.Response.StatusCode);
        Assert.Equal("Bearer", context.Response.Headers.WWWAuthenticate.ToString());
        string body = await ReadBodyAsync(context);
        Assert.DoesNotContain(expectedToken, body, StringComparison.Ordinal);
    }

    [Fact]
    public async Task MutationAcceptsDedicatedAiToken()
    {
        const string expectedToken = "dedicated-ai-token";
        bool nextCalled = false;
        var middleware = new AiMutationAuthorizationMiddleware(_ =>
        {
            nextCalled = true;
            return Task.CompletedTask;
        });
        DefaultHttpContext context = CreateContext("POST");
        context.Request.Headers.Authorization = $"Bearer {expectedToken}";

        await middleware.InvokeAsync(
            context,
            BuildConfiguration((AiMutationAuthorizationMiddleware.PrimaryTokenConfigurationKey, expectedToken)));

        Assert.True(nextCalled);
        Assert.Equal(StatusCodes.Status200OK, context.Response.StatusCode);
    }

    [Fact]
    public async Task SensitiveReadAcceptsDedicatedAiToken()
    {
        const string expectedToken = "dedicated-ai-token";
        bool nextCalled = false;
        var middleware = new AiMutationAuthorizationMiddleware(_ =>
        {
            nextCalled = true;
            return Task.CompletedTask;
        });
        DefaultHttpContext context = CreateContext("GET", "/api/v1/ai/status");
        context.Request.Headers.Authorization = $"Bearer {expectedToken}";

        await middleware.InvokeAsync(
            context,
            BuildConfiguration((AiMutationAuthorizationMiddleware.PrimaryTokenConfigurationKey, expectedToken)));

        Assert.True(nextCalled);
        Assert.Equal(StatusCodes.Status200OK, context.Response.StatusCode);
    }

    [Fact]
    public async Task CommonAuthorizationSatisfiesBoosterControllerGuard()
    {
        const string expectedToken = "dedicated-ai-token";
        IConfiguration configuration = BuildConfiguration(
            (AiMutationAuthorizationMiddleware.PrimaryTokenConfigurationKey, expectedToken));
        bool nextCalled = false;
        var boosterGuard = new BoosterProjectionAccessGuard(configuration);
        var middleware = new AiMutationAuthorizationMiddleware(context =>
        {
            boosterGuard.Require(context.Request);
            nextCalled = true;
            return Task.CompletedTask;
        });
        DefaultHttpContext context = CreateContext("GET", "/api/v1/ai/booster/leaderboard-projection");
        context.Request.Headers.Authorization = $"Bearer {expectedToken}";

        await middleware.InvokeAsync(context, configuration);

        Assert.True(nextCalled);
        Assert.Equal(StatusCodes.Status200OK, context.Response.StatusCode);
    }

    [Fact]
    public async Task MutationAcceptsFleetTokenAsCompatibilityFallback()
    {
        const string expectedToken = "fleet-compatibility-token";
        bool nextCalled = false;
        var middleware = new AiMutationAuthorizationMiddleware(_ =>
        {
            nextCalled = true;
            return Task.CompletedTask;
        });
        DefaultHttpContext context = CreateContext("DELETE");
        context.Request.Headers.Authorization = $"Bearer {expectedToken}";

        await middleware.InvokeAsync(
            context,
            BuildConfiguration(
                (AiMutationAuthorizationMiddleware.PrimaryTokenConfigurationKey, string.Empty),
                (AiMutationAuthorizationMiddleware.FallbackTokenConfigurationKey, expectedToken)));

        Assert.True(nextCalled);
        Assert.Equal(StatusCodes.Status200OK, context.Response.StatusCode);
    }

    [Fact]
    public async Task DedicatedAiTokenTakesPrecedenceOverFleetFallback()
    {
        bool nextCalled = false;
        var middleware = new AiMutationAuthorizationMiddleware(_ =>
        {
            nextCalled = true;
            return Task.CompletedTask;
        });
        DefaultHttpContext context = CreateContext("POST");
        context.Request.Headers.Authorization = "Bearer old-fleet-token";

        await middleware.InvokeAsync(
            context,
            BuildConfiguration(
                (AiMutationAuthorizationMiddleware.PrimaryTokenConfigurationKey, "dedicated-ai-token"),
                (AiMutationAuthorizationMiddleware.FallbackTokenConfigurationKey, "old-fleet-token")));

        Assert.False(nextCalled);
        Assert.Equal(StatusCodes.Status401Unauthorized, context.Response.StatusCode);
    }

    private static DefaultHttpContext CreateContext(string method, string path = "/api/v1/ai/session/events")
    {
        var context = new DefaultHttpContext();
        context.Request.Method = method;
        context.Request.Path = path;
        context.Response.Body = new MemoryStream();
        return context;
    }

    private static IConfiguration BuildConfiguration(params (string Key, string Value)[] values)
        => new ConfigurationBuilder()
            .AddInMemoryCollection(values.ToDictionary(item => item.Key, item => (string?)item.Value))
            .Build();

    private static async Task<JsonDocument> ReadProblemAsync(DefaultHttpContext context)
    {
        string body = await ReadBodyAsync(context);
        return JsonDocument.Parse(body);
    }

    private static async Task<string> ReadBodyAsync(DefaultHttpContext context)
    {
        context.Response.Body.Position = 0;
        using var reader = new StreamReader(context.Response.Body, leaveOpen: true);
        return await reader.ReadToEndAsync();
    }
}
