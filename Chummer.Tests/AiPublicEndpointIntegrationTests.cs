using System.Net;
using System.Net.Http.Headers;
using System.Text.Json;
using Chummer.Run.AI.Security;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Hosting.Server;
using Microsoft.AspNetCore.Hosting.Server.Features;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Xunit;

namespace Chummer.Tests;

public sealed class AiPublicEndpointIntegrationTests
{
    [Fact]
    public async Task PublicEndpointsAreSanitizedAndSensitiveReadsRequireBearerAuthorization()
    {
        const string token = "integration-private-token";
        await using WebApplication app = await StartAppAsync(token);
        using HttpClient client = CreateClient(app);

        using HttpResponseMessage healthResponse = await client.GetAsync(AiPublicEndpoints.HealthPath);
        Assert.Equal(HttpStatusCode.OK, healthResponse.StatusCode);
        using JsonDocument health = JsonDocument.Parse(await healthResponse.Content.ReadAsStringAsync());
        Assert.Equal(2, health.RootElement.EnumerateObject().Count());
        Assert.Equal("chummer.run.ai", health.RootElement.GetProperty("service").GetString());
        Assert.Equal("ok", health.RootElement.GetProperty("status").GetString());

        using HttpResponseMessage capabilitiesResponse = await client.GetAsync(AiPublicEndpoints.CapabilitiesPath);
        Assert.Equal(HttpStatusCode.OK, capabilitiesResponse.StatusCode);
        string capabilitiesBody = await capabilitiesResponse.Content.ReadAsStringAsync();
        using JsonDocument capabilities = JsonDocument.Parse(capabilitiesBody);
        Assert.Equal(4, capabilities.RootElement.EnumerateObject().Count());
        Assert.Equal("bearer_required", capabilities.RootElement.GetProperty("protectedRouteAuthorization").GetString());
        Assert.DoesNotContain("provider", capabilitiesBody, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("prompt", capabilitiesBody, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("session", capabilitiesBody, StringComparison.OrdinalIgnoreCase);

        using var headRequest = new HttpRequestMessage(HttpMethod.Head, AiPublicEndpoints.HealthPath);
        using HttpResponseMessage headResponse = await client.SendAsync(headRequest);
        Assert.Equal(HttpStatusCode.OK, headResponse.StatusCode);
        Assert.Empty(await headResponse.Content.ReadAsByteArrayAsync());

        using HttpResponseMessage anonymousStatus = await client.GetAsync("/api/v1/ai/status");
        Assert.Equal(HttpStatusCode.Unauthorized, anonymousStatus.StatusCode);
        Assert.Equal("Bearer", anonymousStatus.Headers.WwwAuthenticate.Single().Scheme);

        using HttpResponseMessage publicPrefix = await client.GetAsync("/api/health/details");
        Assert.Equal(HttpStatusCode.Unauthorized, publicPrefix.StatusCode);

        client.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", token);
        using HttpResponseMessage authorizedStatus = await client.GetAsync("/api/v1/ai/status");
        Assert.Equal(HttpStatusCode.OK, authorizedStatus.StatusCode);
        using JsonDocument status = JsonDocument.Parse(await authorizedStatus.Content.ReadAsStringAsync());
        Assert.True(status.RootElement.GetProperty("internalOnly").GetBoolean());
    }

    [Fact]
    public async Task SensitiveReadFailsClosedWithoutConfiguredCredentialWhilePublicHealthStaysAvailable()
    {
        await using WebApplication app = await StartAppAsync(string.Empty);
        using HttpClient client = CreateClient(app);

        using HttpResponseMessage health = await client.GetAsync(AiPublicEndpoints.HealthPath);
        Assert.Equal(HttpStatusCode.OK, health.StatusCode);

        using HttpResponseMessage sensitive = await client.GetAsync("/api/v1/ai/conversations/private-session");
        Assert.Equal(HttpStatusCode.ServiceUnavailable, sensitive.StatusCode);
        Assert.Equal("application/problem+json", sensitive.Content.Headers.ContentType?.MediaType);
    }

    private static async Task<WebApplication> StartAppAsync(string configuredToken)
    {
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        builder.Configuration.AddInMemoryCollection(new Dictionary<string, string?>
        {
            [AiMutationAuthorizationMiddleware.PrimaryTokenConfigurationKey] = configuredToken,
            [AiMutationAuthorizationMiddleware.FallbackTokenConfigurationKey] = string.Empty
        });
        builder.WebHost.ConfigureKestrel(options => options.Listen(IPAddress.Loopback, 0));

        WebApplication app = builder.Build();
        app.UseMiddleware<AiMutationAuthorizationMiddleware>();
        app.MapAiPublicEndpoints();
        app.MapGet("/api/v1/ai/status", (HttpContext context) => Results.Ok(new
        {
            internalOnly = context.Items.Count > 0
        }));
        app.MapGet("/api/v1/ai/conversations/{sessionId}", () => Results.Ok());
        app.MapGet("/api/health/details", () => Results.Ok());
        await app.StartAsync();
        return app;
    }

    private static HttpClient CreateClient(WebApplication app)
    {
        IServer server = app.Services.GetRequiredService<IServer>();
        IServerAddressesFeature addresses = server.Features.Get<IServerAddressesFeature>()
            ?? throw new InvalidOperationException("Kestrel did not expose a bound address.");
        return new HttpClient
        {
            BaseAddress = new Uri(addresses.Addresses.Single())
        };
    }
}
