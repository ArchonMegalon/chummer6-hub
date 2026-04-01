using Chummer.Run.Api;
using Microsoft.AspNetCore.Http;
using Xunit;

namespace Chummer.Tests;

public sealed class HubApiGuardrailPolicyTests
{
    [Fact]
    public void ReleaseBundleUploadUsesFileTransferBucket()
    {
        var context = new DefaultHttpContext();
        context.Request.Method = HttpMethods.Post;
        context.Request.Path = "/api/internal/releases/bundles";

        string bucket = HubApiGuardrailPolicy.ResolveRateLimitBucket(context.Request);

        Assert.Equal(HubApiGuardrailPolicy.FileTransferBucket, bucket);
    }

    [Fact]
    public void ReleaseBundleUploadUsesDedicatedBodyLimitAndTimeout()
    {
        var context = new DefaultHttpContext();
        context.Request.Method = HttpMethods.Post;
        context.Request.Path = "/api/internal/releases/bundles";
        HubApiGuardrailOptions options = new()
        {
            MaxReleaseBundleBodyBytes = 123456789,
            ReleaseBundleTimeout = TimeSpan.FromMinutes(9)
        };

        long? bodyLimit = HubApiGuardrailPolicy.ResolveRequestBodyLimit(context.Request, options);
        TimeSpan timeout = HubApiGuardrailPolicy.ResolveTimeout(context.Request, options);

        Assert.Equal(123456789, bodyLimit);
        Assert.Equal(TimeSpan.FromMinutes(9), timeout);
    }
}
