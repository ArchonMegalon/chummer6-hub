using Microsoft.AspNetCore.Http;

namespace Chummer.Run.Api;

public static class HubApiGuardrailPolicy
{
    public const string ApiReadBucket = "api-read";
    public const string ApiWriteBucket = "api-write";
    public const string PublicPageBucket = "public-page";
    public const string FileTransferBucket = "file-transfer";

    public static string ResolveRateLimitBucket(HttpRequest request)
    {
        if (IsFileTransferPath(request.Path))
        {
            return FileTransferBucket;
        }

        if (request.Path.StartsWithSegments("/api", StringComparison.OrdinalIgnoreCase))
        {
            return IsWriteMethod(request.Method) ? ApiWriteBucket : ApiReadBucket;
        }

        return PublicPageBucket;
    }

    public static long? ResolveRequestBodyLimit(HttpRequest request, HubApiGuardrailOptions options)
    {
        ArgumentNullException.ThrowIfNull(request);
        ArgumentNullException.ThrowIfNull(options);

        return IsBodylessMethod(request.Method)
            ? null
            : IsMultipartSupportPath(request.Path)
                ? options.MaxMultipartBodyBytes
                : options.MaxJsonBodyBytes;
    }

    public static TimeSpan ResolveTimeout(HttpRequest request, HubApiGuardrailOptions options)
    {
        ArgumentNullException.ThrowIfNull(request);
        ArgumentNullException.ThrowIfNull(options);

        return IsExtendedTimeoutPath(request.Path)
            ? options.ExtendedRequestTimeout
            : options.DefaultRequestTimeout;
    }

    public static bool IsExtendedTimeoutPath(PathString path)
        => IsMultipartSupportPath(path)
           || IsFileTransferPath(path);

    public static bool IsMultipartSupportPath(PathString path)
        => path.StartsWithSegments("/api/v1/support/cases/form", StringComparison.OrdinalIgnoreCase)
           || path.StartsWithSegments("/contact/submit", StringComparison.OrdinalIgnoreCase);

    public static bool IsFileTransferPath(PathString path)
        => path.StartsWithSegments("/downloads/file", StringComparison.OrdinalIgnoreCase)
           || path.StartsWithSegments("/downloads/files", StringComparison.OrdinalIgnoreCase)
           || path.StartsWithSegments("/downloads/get", StringComparison.OrdinalIgnoreCase);

    private static bool IsBodylessMethod(string method)
        => HttpMethods.IsGet(method)
           || HttpMethods.IsHead(method)
           || HttpMethods.IsOptions(method)
           || HttpMethods.IsTrace(method);

    private static bool IsWriteMethod(string method)
        => HttpMethods.IsPost(method)
           || HttpMethods.IsPut(method)
           || HttpMethods.IsPatch(method)
           || HttpMethods.IsDelete(method);
}
