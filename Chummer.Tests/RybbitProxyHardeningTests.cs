using Chummer.Run.Api.Services;
using Xunit;

namespace Chummer.Tests;

public sealed class RybbitProxyHardeningTests
{
    [Fact]
    public void PublicRybbitProxyUsesStrictHeaderAllowlistsAndHttpsOnlyOrigin()
    {
        string program = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Program.cs"));

        Assert.Contains("app.MapMethods(\"/api/rybbit/{**proxyPath}\"", program, StringComparison.Ordinal);
        Assert.Contains("CreateClient(\"RybbitProxy\")", program, StringComparison.Ordinal);
        Assert.Contains("parsedOrigin.Scheme != Uri.UriSchemeHttps", program, StringComparison.Ordinal);
        Assert.DoesNotContain("parsedOrigin.Scheme != Uri.UriSchemeHttp && parsedOrigin.Scheme != Uri.UriSchemeHttps", program, StringComparison.Ordinal);

        Assert.Contains("RybbitProxyPolicy.NormalizeProxyPath(proxyPath)", program, StringComparison.Ordinal);
        Assert.Contains("RybbitProxyPolicy.ShouldForwardRequestHeader(key)", program, StringComparison.Ordinal);
        Assert.Contains("RybbitProxyPolicy.ShouldForwardResponseHeader(header.Key)", program, StringComparison.Ordinal);
    }

    [Fact]
    public void PublicRybbitProxyPolicyNeverForwardsCredentialsOrUpstreamCookies()
    {
        foreach (string header in new[]
                 {
                     "Authorization",
                     "Cookie",
                     "Proxy-Authorization",
                     "Forwarded",
                     "Host",
                     "Connection",
                     "Transfer-Encoding",
                     "X-Forwarded-For",
                     "X-Forwarded-Host",
                     "X-Forwarded-Proto"
                 })
        {
            Assert.False(RybbitProxyPolicy.ShouldForwardRequestHeader(header), $"{header} must not leave chummer.run.");
        }

        foreach (string header in new[]
                 {
                     "Set-Cookie",
                     "Proxy-Authenticate",
                     "Proxy-Authorization",
                     "Connection",
                     "Transfer-Encoding"
                 })
        {
            Assert.False(RybbitProxyPolicy.ShouldForwardResponseHeader(header), $"{header} must not enter chummer.run from analytics.");
        }

        Assert.True(RybbitProxyPolicy.ShouldForwardRequestHeader("Accept"));
        Assert.True(RybbitProxyPolicy.ShouldForwardRequestHeader("Content-Type"));
        Assert.True(RybbitProxyPolicy.ShouldForwardRequestHeader("User-Agent"));
        Assert.True(RybbitProxyPolicy.ShouldForwardResponseHeader("Content-Type"));
        Assert.True(RybbitProxyPolicy.ShouldForwardResponseHeader("ETag"));
    }

    [Theory]
    [InlineData("", "")]
    [InlineData("event", "event")]
    [InlineData("event name", "event%20name")]
    [InlineData("v1/events", "v1/events")]
    public void PublicRybbitProxyPolicyNormalizesSafeRelativePaths(string input, string expected)
    {
        Assert.Equal(expected, RybbitProxyPolicy.NormalizeProxyPath(input));
    }

    [Theory]
    [InlineData("https://evil.example/collect")]
    [InlineData("../collect")]
    [InlineData("%2e%2e/collect")]
    [InlineData("%")]
    public void PublicRybbitProxyPolicyRejectsAbsoluteParentAndMalformedPaths(string input)
    {
        Assert.Null(RybbitProxyPolicy.NormalizeProxyPath(input));
    }

    [Fact]
    public void PublicLayoutDoesNotLoadRybbitOnSignedInOrSensitiveSurfaces()
    {
        string layout = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Views", "Shared", "_Layout.cshtml"));

        Assert.Contains("var authSurface =", layout, StringComparison.Ordinal);
        Assert.Contains("!authSurface", layout, StringComparison.Ordinal);
        Assert.Contains("\"/account/**\"", layout, StringComparison.Ordinal);
        Assert.Contains("\"/downloads/file/**\"", layout, StringComparison.Ordinal);
        Assert.Contains("\"/downloads/install/**\"", layout, StringComparison.Ordinal);
        Assert.Contains("\"/login\"", layout, StringComparison.Ordinal);
        Assert.Contains("\"/signup\"", layout, StringComparison.Ordinal);
    }

}
