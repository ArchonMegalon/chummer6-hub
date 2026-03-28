using System.IO;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.RateLimiting;
using Chummer.Run.Api;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Http.Features;

namespace RunServicesVerification;

internal static class HubApiRuntimeGuardrailVerification
{
    public static async Task RunAsync()
    {
        VerifyPolicyBucketsAndLimits();
        VerifyRateLimiterRejectsRepeatedApiWrites();
        await VerifyOversizedPayloadIsRejectedAsync();
        await VerifyTimedOutRequestReturnsServiceUnavailableAsync();
    }

    private static void VerifyPolicyBucketsAndLimits()
    {
        HubApiGuardrailOptions options = new();
        DefaultHttpContext jsonContext = new();
        jsonContext.Request.Method = HttpMethods.Post;
        jsonContext.Request.Path = "/api/v1/support/cases";

        DefaultHttpContext multipartContext = new();
        multipartContext.Request.Method = HttpMethods.Post;
        multipartContext.Request.Path = "/api/v1/support/cases/form";

        DefaultHttpContext downloadContext = new();
        downloadContext.Request.Method = HttpMethods.Get;
        downloadContext.Request.Path = "/downloads/file/preview-linux-x64";

        VerificationAssert.Equal(HubApiGuardrailPolicy.ApiWriteBucket, HubApiGuardrailPolicy.ResolveRateLimitBucket(jsonContext.Request), "API writes should use the write limiter bucket.");
        VerificationAssert.Equal(HubApiGuardrailPolicy.FileTransferBucket, HubApiGuardrailPolicy.ResolveRateLimitBucket(downloadContext.Request), "Download routes should use the file-transfer limiter bucket.");
        VerificationAssert.Equal(options.MaxJsonBodyBytes, HubApiGuardrailPolicy.ResolveRequestBodyLimit(jsonContext.Request, options) ?? -1L, "JSON API writes should use the compact body limit.");
        VerificationAssert.Equal(options.MaxMultipartBodyBytes, HubApiGuardrailPolicy.ResolveRequestBodyLimit(multipartContext.Request, options) ?? -1L, "Multipart support intake should use the larger body limit.");
        VerificationAssert.Equal(options.ExtendedRequestTimeout, HubApiGuardrailPolicy.ResolveTimeout(downloadContext.Request, options), "Downloads should use the extended request timeout budget.");
    }

    private static void VerifyRateLimiterRejectsRepeatedApiWrites()
    {
        HubApiGuardrailOptions options = new()
        {
            ApiWriteRequestsPerMinute = 2,
            ApiReadRequestsPerMinute = 5,
            PublicPageRequestsPerMinute = 5,
            FileTransferRequestsPerMinute = 5
        };

        using PartitionedRateLimiter<HttpContext> limiter = HubApiRateLimiterFactory.Create(options);
        using var first = limiter.AttemptAcquire(CreateWriteContext("198.51.100.10"), 1);
        using var second = limiter.AttemptAcquire(CreateWriteContext("198.51.100.10"), 1);
        using var third = limiter.AttemptAcquire(CreateWriteContext("198.51.100.10"), 1);
        using var otherClient = limiter.AttemptAcquire(CreateWriteContext("198.51.100.11"), 1);

        VerificationAssert.True(first.IsAcquired, "The first write request should acquire a permit.");
        VerificationAssert.True(second.IsAcquired, "The second write request should acquire a permit.");
        VerificationAssert.True(!third.IsAcquired, "The limiter should reject the third write within the same window.");
        VerificationAssert.True(otherClient.IsAcquired, "A different client should receive an independent limiter partition.");
    }

    private static async Task VerifyOversizedPayloadIsRejectedAsync()
    {
        HubApiGuardrailOptions options = new()
        {
            MaxJsonBodyBytes = 64,
            MaxRequestBodyBytes = 1024
        };
        HubApiRequestGuardrailMiddleware middleware = new(static _ => Task.CompletedTask, options);
        DefaultHttpContext context = CreateWriteContext("198.51.100.15");
        context.Request.ContentLength = 128;
        context.Request.Body = new MemoryStream(Encoding.UTF8.GetBytes("{\"title\":\"too-large\"}"));
        context.Response.Body = new MemoryStream();
        context.Features.Set<IHttpMaxRequestBodySizeFeature>(new FakeMaxRequestBodySizeFeature());

        await middleware.InvokeAsync(context);

        VerificationAssert.Equal(StatusCodes.Status413PayloadTooLarge, context.Response.StatusCode, "Oversized request bodies should be rejected before controller execution.");
        context.Response.Body.Position = 0;
        string response = await new StreamReader(context.Response.Body).ReadToEndAsync();
        VerificationAssert.True(response.Contains("request-too-large", StringComparison.Ordinal), "Oversized responses should emit a request-too-large problem type.");
    }

    private static async Task VerifyTimedOutRequestReturnsServiceUnavailableAsync()
    {
        HubApiGuardrailOptions options = new()
        {
            DefaultRequestTimeout = TimeSpan.FromMilliseconds(25),
            ExtendedRequestTimeout = TimeSpan.FromMilliseconds(50)
        };
        HubApiRequestGuardrailMiddleware middleware = new(async context =>
        {
            await Task.Delay(TimeSpan.FromSeconds(1), context.RequestAborted);
        }, options);
        DefaultHttpContext context = CreateWriteContext("198.51.100.20");
        context.Request.ContentLength = 16;
        context.Request.Body = new MemoryStream(Encoding.UTF8.GetBytes("{\"ok\":true}"));
        context.Response.Body = new MemoryStream();

        await middleware.InvokeAsync(context);

        VerificationAssert.Equal(StatusCodes.Status503ServiceUnavailable, context.Response.StatusCode, "Timed-out requests should return a service-unavailable guardrail response.");
        context.Response.Body.Position = 0;
        using JsonDocument payload = await JsonDocument.ParseAsync(context.Response.Body);
        VerificationAssert.Equal("https://chummer.run/problems/request-timeout", payload.RootElement.GetProperty("type").GetString() ?? string.Empty, "Timed-out requests should emit the timeout problem type.");
    }

    private static DefaultHttpContext CreateWriteContext(string ipAddress)
    {
        DefaultHttpContext context = new();
        context.Request.Method = HttpMethods.Post;
        context.Request.Path = "/api/v1/support/cases";
        context.Connection.RemoteIpAddress = System.Net.IPAddress.Parse(ipAddress);
        return context;
    }

    private sealed class FakeMaxRequestBodySizeFeature : IHttpMaxRequestBodySizeFeature
    {
        public bool IsReadOnly => false;

        public long? MaxRequestBodySize { get; set; }
    }
}
