using System.Threading.RateLimiting;
using Microsoft.AspNetCore.Http;

namespace Chummer.Run.Api;

public static class HubApiRateLimiterFactory
{
    public static PartitionedRateLimiter<HttpContext> Create(HubApiGuardrailOptions options)
    {
        ArgumentNullException.ThrowIfNull(options);

        return PartitionedRateLimiter.Create<HttpContext, string>(context =>
        {
            string bucket = HubApiGuardrailPolicy.ResolveRateLimitBucket(context.Request);
            string client = ResolveClientKey(context);
            string partitionKey = $"{bucket}:{client}";

            return RateLimitPartition.GetSlidingWindowLimiter(
                partitionKey,
                _ => new SlidingWindowRateLimiterOptions
                {
                    PermitLimit = ResolvePermitLimit(bucket, options),
                    QueueProcessingOrder = QueueProcessingOrder.OldestFirst,
                    QueueLimit = options.RateLimitQueueLimit,
                    Window = TimeSpan.FromMinutes(1),
                    SegmentsPerWindow = Math.Max(1, options.RateLimitSegmentsPerWindow),
                    AutoReplenishment = true
                });
        });
    }

    public static int ResolvePermitLimit(string bucket, HubApiGuardrailOptions options)
        => bucket switch
        {
            HubApiGuardrailPolicy.ApiReadBucket => options.ApiReadRequestsPerMinute,
            HubApiGuardrailPolicy.ApiWriteBucket => options.ApiWriteRequestsPerMinute,
            HubApiGuardrailPolicy.FileTransferBucket => options.FileTransferRequestsPerMinute,
            _ => options.PublicPageRequestsPerMinute
        };

    public static string ResolveClientKey(HttpContext context)
    {
        ArgumentNullException.ThrowIfNull(context);

        // ForwardedHeadersMiddleware is the only component allowed to translate a
        // trusted proxy header into RemoteIpAddress. Reading X-Forwarded-For here
        // would let an untrusted caller choose its own rate-limit partition.
        return context.Connection.RemoteIpAddress?.ToString() ?? "remote-ip-unavailable";
    }
}
