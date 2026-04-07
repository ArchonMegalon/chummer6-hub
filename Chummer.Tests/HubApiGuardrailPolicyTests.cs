using Chummer.Run.Api;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Http.Features;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Options;
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
    public void ReleaseBundleUploadSessionRoutesUseFileTransferBucket()
    {
        var context = new DefaultHttpContext();
        context.Request.Method = HttpMethods.Post;
        context.Request.Path = "/api/internal/releases/upload-sessions/demo/files";

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

    [Fact]
    public void ReleaseBundleUploadSessionRoutesUseDedicatedBodyLimitAndTimeout()
    {
        var context = new DefaultHttpContext();
        context.Request.Method = HttpMethods.Post;
        context.Request.Path = "/api/internal/releases/upload-sessions/demo/chunks";
        HubApiGuardrailOptions options = new()
        {
            MaxReleaseBundleBodyBytes = 234567890,
            ReleaseBundleTimeout = TimeSpan.FromMinutes(11)
        };

        long? bodyLimit = HubApiGuardrailPolicy.ResolveRequestBodyLimit(context.Request, options);
        TimeSpan timeout = HubApiGuardrailPolicy.ResolveTimeout(context.Request, options);

        Assert.Equal(234567890, bodyLimit);
        Assert.Equal(TimeSpan.FromMinutes(11), timeout);
    }

    [Fact]
    public void RuntimeGuardrailsRaiseMultipartAndRequestCapsForReleaseBundles()
    {
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        builder.Configuration.AddInMemoryCollection(new Dictionary<string, string?>
        {
            ["CHUMMER_API_MAX_MULTIPART_BODY_BYTES"] = (45 * 1024 * 1024L).ToString(),
            ["CHUMMER_API_MAX_RELEASE_BUNDLE_BODY_BYTES"] = (256 * 1024 * 1024L).ToString(),
            ["CHUMMER_API_MAX_REQUEST_BODY_BYTES"] = (50 * 1024 * 1024L).ToString()
        });

        builder.AddHubApiRuntimeGuardrails();

        using ServiceProvider provider = builder.Services.BuildServiceProvider();
        FormOptions formOptions = provider.GetRequiredService<IOptions<FormOptions>>().Value;
        HubApiGuardrailOptions guardrailOptions = provider.GetRequiredService<HubApiGuardrailOptions>();

        Assert.Equal(guardrailOptions.MaxReleaseBundleBodyBytes, formOptions.MultipartBodyLengthLimit);
        Assert.True(guardrailOptions.MaxReleaseBundleBodyBytes > guardrailOptions.MaxMultipartBodyBytes);
        Assert.True(guardrailOptions.MaxReleaseBundleBodyBytes > guardrailOptions.MaxRequestBodyBytes);
    }
}
