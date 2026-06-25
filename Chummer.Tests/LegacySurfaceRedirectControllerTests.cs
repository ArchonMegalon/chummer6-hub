using Chummer.Run.Api.Controllers;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Configuration;
using Xunit;

namespace Chummer.Tests;

public sealed class LegacySurfaceRedirectControllerTests
{
    [Theory]
    [InlineData("support", "/contact")]
    [InlineData("blazor", "/downloads")]
    public async Task PublicConvenienceRoutesRedirectToLiveFlagshipSurfaces(string route, string expectedUrl)
    {
        var controller = new LegacySurfaceRedirectController();

        IActionResult result = route switch
        {
            "support" => controller.Support(),
            "blazor" => await controller.Workbench(path: null, CancellationToken.None),
            _ => throw new ArgumentOutOfRangeException(nameof(route), route, null)
        };

        var redirect = Assert.IsType<RedirectResult>(result);
        Assert.Equal(expectedUrl, redirect.Url);
    }

    [Fact]
    public async Task BrowserSurfaceProxyReturnsFirstPartyFallbackWhenUpstreamFails()
    {
        var controller = CreateBrowserController(new StaticHttpClientFactory(new HttpClient(new StaticHandler(
            new HttpResponseMessage(System.Net.HttpStatusCode.InternalServerError)))));

        IActionResult result = await controller.Workbench(path: null, CancellationToken.None);

        var content = Assert.IsType<ContentResult>(result);
        Assert.Equal("text/html", content.ContentType);
        Assert.Contains("Browser preview is not ready right now.", content.Content, StringComparison.Ordinal);
        Assert.Contains("Download Chummer", content.Content, StringComparison.Ordinal);
        Assert.Contains("href=\"/downloads\"", content.Content, StringComparison.Ordinal);
        Assert.DoesNotContain("Unexpected server error", content.Content, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task BrowserSurfaceProxyReturnsFirstPartyFallbackWhenUpstreamIsUnreachable()
    {
        var controller = CreateBrowserController(new StaticHttpClientFactory(new HttpClient(new ThrowingHandler())));

        IActionResult result = await controller.Workbench(path: null, CancellationToken.None);

        var content = Assert.IsType<ContentResult>(result);
        Assert.Contains("Browser preview is not ready right now.", content.Content, StringComparison.Ordinal);
        Assert.Contains("href=\"/status\"", content.Content, StringComparison.Ordinal);
    }

    private static LegacySurfaceRedirectController CreateBrowserController(IHttpClientFactory factory)
    {
        var configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_PUBLIC_BLAZOR_PROXY_URL"] = "https://browser.example/blazor/"
            })
            .Build();

        var controller = new LegacySurfaceRedirectController(factory, configuration)
        {
            ControllerContext = new ControllerContext
            {
                HttpContext = new DefaultHttpContext()
            }
        };
        return controller;
    }

    private sealed class StaticHttpClientFactory(HttpClient client) : IHttpClientFactory
    {
        public HttpClient CreateClient(string name) => client;
    }

    private sealed class StaticHandler(HttpResponseMessage response) : HttpMessageHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
            => Task.FromResult(response);
    }

    private sealed class ThrowingHandler : HttpMessageHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
            => throw new HttpRequestException("upstream unavailable");
    }
}
