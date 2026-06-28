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
        if (IsFileTransferPath(request.Path) || IsReleaseBundleUploadPath(request.Path))
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
            : IsReleaseBundleUploadPath(request.Path)
                ? options.MaxReleaseBundleBodyBytes
                : IsMultipartSupportPath(request.Path)
                ? options.MaxMultipartBodyBytes
                : options.MaxJsonBodyBytes;
    }

    public static TimeSpan ResolveTimeout(HttpRequest request, HubApiGuardrailOptions options)
    {
        ArgumentNullException.ThrowIfNull(request);
        ArgumentNullException.ThrowIfNull(options);

        return IsReleaseBundleUploadPath(request.Path)
            ? options.ReleaseBundleTimeout
            : IsExtendedTimeoutPath(request.Path)
            ? options.ExtendedRequestTimeout
            : options.DefaultRequestTimeout;
    }

    public static bool IsExtendedTimeoutPath(PathString path)
        => IsMultipartSupportPath(path)
           || IsFileTransferPath(path)
           || IsBrowserSurfaceProxyPath(path)
           || path.StartsWithSegments("/api/internal/heyy/scam-chat", StringComparison.OrdinalIgnoreCase);

    public static bool IsReleaseBundleUploadPath(PathString path)
        => path.StartsWithSegments("/api/internal/releases/bundles", StringComparison.OrdinalIgnoreCase)
           || path.StartsWithSegments("/api/internal/releases/upload-sessions", StringComparison.OrdinalIgnoreCase);

    public static bool IsMultipartSupportPath(PathString path)
        => path.StartsWithSegments("/api/v1/support/cases/form", StringComparison.OrdinalIgnoreCase)
           || path.StartsWithSegments("/contact/submit", StringComparison.OrdinalIgnoreCase);

    public static bool IsFileTransferPath(PathString path)
        => path.StartsWithSegments("/downloads/file", StringComparison.OrdinalIgnoreCase)
           || path.StartsWithSegments("/downloads/files", StringComparison.OrdinalIgnoreCase)
           || path.StartsWithSegments("/downloads/get", StringComparison.OrdinalIgnoreCase);

    public static bool IsBrowserSurfaceProxyPath(PathString path)
        => path.StartsWithSegments("/blazor", StringComparison.OrdinalIgnoreCase)
           || path.StartsWithSegments("/app", StringComparison.OrdinalIgnoreCase)
           || path.StartsWithSegments("/avalonia", StringComparison.OrdinalIgnoreCase);

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
