using Chummer.Run.Api;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class HubRequestObservabilityMiddlewarePrivacyTests
{
    [Theory]
    [InlineData("0123456789abcdef0123456789abcdef")]
    [InlineData("8c0f8f5e-14c5-4c9f-9dbe-2350fb58f1cc")]
    public async Task InvokeAsync_preserves_standard_opaque_correlation_identifiers(string forwarded)
    {
        HubRequestObservabilityOptions options = new();
        HubRequestObservabilityMiddleware middleware = CreateMiddleware(options);
        DefaultHttpContext context = CreateContext(options, forwarded);

        await middleware.InvokeAsync(context);

        Assert.Equal(forwarded, context.Response.Headers[options.CorrelationHeaderName].ToString());
    }

    [Theory]
    [InlineData("customer-name")]
    [InlineData("private-user@example.com")]
    [InlineData("00000000000000000000000000000000")]
    [InlineData("00000000-0000-0000-0000-000000000000")]
    [InlineData("0123456789abcdef0123456789abcdef-extra")]
    public async Task InvokeAsync_replaces_human_or_nonstandard_correlation_identifiers(string forwarded)
    {
        HubRequestObservabilityOptions options = new();
        HubRequestObservabilityMiddleware middleware = CreateMiddleware(options);
        DefaultHttpContext context = CreateContext(options, forwarded);

        await middleware.InvokeAsync(context);

        string observed = context.Response.Headers[options.CorrelationHeaderName].ToString();
        Assert.NotEqual(forwarded, observed);
        Assert.Matches("^[0-9a-f]{32}$", observed);
    }

    private static HubRequestObservabilityMiddleware CreateMiddleware(
        HubRequestObservabilityOptions options)
        => new(
            context =>
            {
                context.Response.StatusCode = StatusCodes.Status204NoContent;
                return Task.CompletedTask;
            },
            options,
            NullLogger<HubRequestObservabilityMiddleware>.Instance);

    private static DefaultHttpContext CreateContext(
        HubRequestObservabilityOptions options,
        string forwarded)
    {
        DefaultHttpContext context = new();
        context.Request.Method = HttpMethods.Get;
        context.Request.Headers[options.CorrelationHeaderName] = forwarded;
        return context;
    }
}
