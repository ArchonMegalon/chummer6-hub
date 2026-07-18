using System.Text.Json;
using Chummer.Run.Contracts.PublicSurface;

namespace Chummer.Run.Api.Services;

public sealed class PublicReleaseTruthProjectionMiddleware
{
    public const string ProjectionHeaderName = "X-Chummer-Release-Truth";
    public const string DecisionStatusHeaderName = "X-Chummer-Release-Decision-Status";
    public const string AuthoritySnapshotSha256HeaderName =
        "X-Chummer-Release-Authority-Snapshot-Sha256";
    public static readonly object HttpContextItemKey = new();
    private static readonly object AuthoritySnapshotSha256ItemKey = new();

    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web);
    private readonly RequestDelegate _next;

    public PublicReleaseTruthProjectionMiddleware(RequestDelegate next)
    {
        _next = next;
    }

    public async Task InvokeAsync(HttpContext context, IReleaseTruthProjection releaseTruth)
    {
        if (!IsReleaseFacingRoute(context.Request.Path))
        {
            await _next(context);
            return;
        }

        PublicReleaseTruthCapture capture;
        try
        {
            capture = TryResolveGenerationId(context.Request.Path, out string? generationId)
                ? releaseTruth.CaptureGenerationWithAuthority(generationId!)
                : releaseTruth.CaptureWithAuthority();
        }
        catch (Exception exception) when (exception is InvalidDataException or InvalidOperationException)
        {
            // Let the generation-bound controller preserve its established 404
            // behavior for an unknown, unsafe, or unavailable generation.
            await _next(context);
            return;
        }
        PublicReleaseTruthProjectionDto projection = capture.Projection;
        context.Items[HttpContextItemKey] = projection;
        context.Items[AuthoritySnapshotSha256ItemKey] = capture.AuthoritySnapshotSha256;
        byte[] json = JsonSerializer.SerializeToUtf8Bytes(projection, JsonOptions);
        context.Response.Headers[ProjectionHeaderName] = ToBase64Url(json);
        context.Response.Headers[DecisionStatusHeaderName] = projection.ReleaseDecisionStatus;
        context.Response.Headers[AuthoritySnapshotSha256HeaderName] = capture.AuthoritySnapshotSha256;
        context.Response.Headers.Append(
            "Link",
            "</api/v1/public/release-truth>; rel=\"release-truth\"; type=\"application/json\"");
        await _next(context);
    }

    public static PublicReleaseTruthProjectionDto? TryGet(HttpContext? context)
        => context?.Items.TryGetValue(HttpContextItemKey, out object? value) == true
            ? value as PublicReleaseTruthProjectionDto
            : null;

    public static string? TryGetAuthoritySnapshotSha256(HttpContext? context)
        => context?.Items.TryGetValue(AuthoritySnapshotSha256ItemKey, out object? value) == true
            ? value as string
            : null;

    public static bool IsReleaseFacingRoute(PathString path)
    {
        string value = path.Value ?? string.Empty;
        if (value is "/" or "/now" or "/changelog" or "/downloads" or "/status" or "/artifacts" or "/progress")
        {
            return true;
        }

        return value.StartsWith("/downloads/", StringComparison.OrdinalIgnoreCase)
            || value.StartsWith("/api/v1/public/progress", StringComparison.OrdinalIgnoreCase)
            || value.StartsWith("/api/public/progress", StringComparison.OrdinalIgnoreCase)
            || value.Equals("/api/v1/public/weekly-pulse", StringComparison.OrdinalIgnoreCase)
            || value.Equals("/api/public/weekly-pulse", StringComparison.OrdinalIgnoreCase)
            || value.Equals("/api/v1/public/release-truth", StringComparison.OrdinalIgnoreCase)
            || value.Equals("/api/public/release-truth", StringComparison.OrdinalIgnoreCase)
            || value.StartsWith("/api/v1/public/release-truth/g/", StringComparison.OrdinalIgnoreCase)
            || value.StartsWith("/api/public/release-truth/g/", StringComparison.OrdinalIgnoreCase);
    }

    private static bool TryResolveGenerationId(PathString path, out string? generationId)
    {
        string value = path.Value ?? string.Empty;
        foreach (string prefix in new[]
                 {
                     "/downloads/g/",
                     "/api/v1/public/release-truth/g/",
                     "/api/public/release-truth/g/"
                 })
        {
            if (!value.StartsWith(prefix, StringComparison.OrdinalIgnoreCase))
            {
                continue;
            }

            string remainder = value[prefix.Length..];
            int separator = remainder.IndexOf('/');
            generationId = (separator < 0 ? remainder : remainder[..separator]).Trim();
            return generationId.Length > 0;
        }

        generationId = null;
        return false;
    }

    private static string ToBase64Url(byte[] bytes)
        => Convert.ToBase64String(bytes)
            .TrimEnd('=')
            .Replace('+', '-')
            .Replace('/', '_');
}
