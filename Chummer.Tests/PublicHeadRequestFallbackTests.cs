using Xunit;

namespace Chummer.Tests;

public sealed class PublicHeadRequestFallbackTests
{
    [Fact]
    public void PublicEdgeServesHeadFromGetWithoutWritingResponseBodies()
    {
        string program = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Program.cs"));

        Assert.Contains("HttpMethods.IsHead(context.Request.Method)", program, StringComparison.Ordinal);
        Assert.Contains("ShouldServeHeadFromGet(context.Request.Path)", program, StringComparison.Ordinal);
        Assert.Contains("context.Request.Method = HttpMethods.Get;", program, StringComparison.Ordinal);
        Assert.Contains("context.Response.Body = Stream.Null;", program, StringComparison.Ordinal);
        Assert.Contains("context.Response.Body = originalBody;", program, StringComparison.Ordinal);
        Assert.Contains("context.Request.Method = originalMethod;", program, StringComparison.Ordinal);
    }

    [Fact]
    public void PublicEdgeHeadFallbackIsLimitedToPublicRoutesAndHealth()
    {
        string program = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Program.cs"));

        Assert.Contains("static bool ShouldServeHeadFromGet(PathString path)", program, StringComparison.Ordinal);
        Assert.Contains("path.Equals(\"/api/health\", StringComparison.OrdinalIgnoreCase)", program, StringComparison.Ordinal);
        Assert.Contains("!path.StartsWithSegments(\"/api\", StringComparison.OrdinalIgnoreCase)", program, StringComparison.Ordinal);
    }
}
