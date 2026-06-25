using Xunit;
using System.Text.RegularExpressions;

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

        Assert.Contains("HashSet<string> RybbitAllowedRequestHeaders", program, StringComparison.Ordinal);
        Assert.Contains("\"Accept\"", program, StringComparison.Ordinal);
        Assert.Contains("\"Content-Type\"", program, StringComparison.Ordinal);
        Assert.Contains("\"User-Agent\"", program, StringComparison.Ordinal);
        Assert.Contains("return RybbitAllowedRequestHeaders.Contains(headerName)", program, StringComparison.Ordinal);
        var allowedRequestHeaders = ReadCSharpStringSet(program, "RybbitAllowedRequestHeaders");
        Assert.DoesNotContain("Authorization", allowedRequestHeaders);
        Assert.DoesNotContain("Cookie", allowedRequestHeaders);
        Assert.DoesNotContain("Proxy-Authorization", allowedRequestHeaders);
        Assert.DoesNotContain("Forwarded", allowedRequestHeaders);
        Assert.DoesNotContain("X-Forwarded-For", allowedRequestHeaders);
        Assert.DoesNotContain("X-Forwarded-Host", allowedRequestHeaders);
        Assert.DoesNotContain("X-Forwarded-Proto", allowedRequestHeaders);

        Assert.Contains("HashSet<string> RybbitBlockedRequestHeaders", program, StringComparison.Ordinal);
        Assert.Contains("\"Authorization\"", program, StringComparison.Ordinal);
        Assert.Contains("\"Cookie\"", program, StringComparison.Ordinal);
        Assert.Contains("\"Proxy-Authorization\"", program, StringComparison.Ordinal);
        Assert.Contains("\"X-Forwarded-For\"", program, StringComparison.Ordinal);
        Assert.Contains("if (!ShouldForwardRybbitRequestHeader(key))", program, StringComparison.Ordinal);

        Assert.Contains("HashSet<string> RybbitAllowedResponseHeaders", program, StringComparison.Ordinal);
        Assert.Contains("\"Content-Type\"", program, StringComparison.Ordinal);
        Assert.Contains("\"ETag\"", program, StringComparison.Ordinal);
        Assert.Contains("return RybbitAllowedResponseHeaders.Contains(headerName)", program, StringComparison.Ordinal);
        var allowedResponseHeaders = ReadCSharpStringSet(program, "RybbitAllowedResponseHeaders");
        Assert.DoesNotContain("Set-Cookie", allowedResponseHeaders);
        Assert.DoesNotContain("Proxy-Authenticate", allowedResponseHeaders);
        Assert.DoesNotContain("Proxy-Authorization", allowedResponseHeaders);
        Assert.DoesNotContain("Transfer-Encoding", allowedResponseHeaders);
        Assert.DoesNotContain("Connection", allowedResponseHeaders);

        Assert.Contains("HashSet<string> RybbitBlockedResponseHeaders", program, StringComparison.Ordinal);
        Assert.Contains("\"Set-Cookie\"", program, StringComparison.Ordinal);
        Assert.Contains("\"Proxy-Authenticate\"", program, StringComparison.Ordinal);
        Assert.Contains("if (ShouldForwardRybbitResponseHeader(header.Key))", program, StringComparison.Ordinal);
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

    private static HashSet<string> ReadCSharpStringSet(string source, string setName)
    {
        var match = Regex.Match(
            source,
            $@"HashSet<string>\s+{Regex.Escape(setName)}\s*=\s*new\([^)]*\)\s*\{{(?<body>.*?)\}};",
            RegexOptions.Singleline);
        Assert.True(match.Success, $"Could not find {setName} in Program.cs.");

        return Regex.Matches(match.Groups["body"].Value, "\"([^\"]+)\"")
            .Select(static item => item.Groups[1].Value)
            .ToHashSet(StringComparer.OrdinalIgnoreCase);
    }
}
