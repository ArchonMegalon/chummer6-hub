using System.Text;
using Chummer.Run.Api;
using Microsoft.AspNetCore.Http;
using Xunit;

namespace Chummer.Tests;

public sealed class HubApiRequestGuardrailMiddlewareTests
{
    [Fact]
    public async Task BrowserSurfaceProxyRouteUsesExtendedTimeoutBudgetInMiddleware()
    {
        var context = new DefaultHttpContext();
        context.Request.Method = HttpMethods.Get;
        context.Request.Path = "/blazor/workbench";
        await using var responseBody = new MemoryStream();
        context.Response.Body = responseBody;

        var options = new HubApiGuardrailOptions
        {
            DefaultRequestTimeout = TimeSpan.FromMilliseconds(50),
            ExtendedRequestTimeout = TimeSpan.FromSeconds(5)
        };

        var middleware = new HubApiRequestGuardrailMiddleware(
            async innerContext =>
            {
                await Task.Delay(100, innerContext.RequestAborted);
                innerContext.Response.StatusCode = StatusCodes.Status204NoContent;
            },
            options);

        await middleware.InvokeAsync(context);

        Assert.Equal(StatusCodes.Status204NoContent, context.Response.StatusCode);
        Assert.Equal(0, responseBody.Length);
    }

    [Fact]
    public async Task NonBrowserPublicRouteStillFailsClosedWhenOperationBudgetIsExceeded()
    {
        var context = new DefaultHttpContext();
        context.Request.Method = HttpMethods.Get;
        context.Request.Path = "/status";
        await using var responseBody = new MemoryStream();
        context.Response.Body = responseBody;

        var options = new HubApiGuardrailOptions
        {
            DefaultRequestTimeout = TimeSpan.FromMilliseconds(50),
            ExtendedRequestTimeout = TimeSpan.FromSeconds(5)
        };

        var middleware = new HubApiRequestGuardrailMiddleware(
            async innerContext =>
            {
                await Task.Delay(TimeSpan.FromSeconds(5), innerContext.RequestAborted);
                innerContext.Response.StatusCode = StatusCodes.Status204NoContent;
            },
            options);

        await middleware.InvokeAsync(context);

        Assert.Equal(StatusCodes.Status503ServiceUnavailable, context.Response.StatusCode);
        responseBody.Position = 0;
        string payload = Encoding.UTF8.GetString(responseBody.ToArray());
        Assert.Contains("Hub request exceeded the operation budget.", payload, StringComparison.Ordinal);
        Assert.Contains("This route must complete within", payload, StringComparison.Ordinal);
    }
}
