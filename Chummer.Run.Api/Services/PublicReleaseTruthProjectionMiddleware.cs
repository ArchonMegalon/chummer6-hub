using System.Text.Json;
using Chummer.Run.Contracts.PublicSurface;

namespace Chummer.Run.Api.Services;

public sealed class PublicReleaseTruthProjectionMiddleware
{
    public const string ProjectionHeaderName = "X-Chummer-Release-Truth";
    public const string DecisionStatusHeaderName = "X-Chummer-Release-Decision-Status";
    public const string AuthoritySnapshotSha256HeaderName =
        "X-Chummer-Release-Authority-Snapshot-Sha256";
    public const string StagedProbeHeaderName = "X-Chummer-Staged-Release-Probe";
    public static readonly object HttpContextItemKey = new();
    private static readonly object AuthoritySnapshotSha256ItemKey = new();

    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web);
    private readonly RequestDelegate _next;

    public PublicReleaseTruthProjectionMiddleware(RequestDelegate next)
    {
        _next = next;
    }

    public async Task InvokeAsync(
        HttpContext context,
        IReleaseTruthProjection releaseTruth,
        ReleaseBundlePromotionService promotions,
        ReleaseShelfGenerationStore shelfStore)
    {
        if (!IsReleaseFacingRoute(context.Request.Path))
        {
            await _next(context);
            return;
        }

        string? stagedProbe = context.Request.Headers[StagedProbeHeaderName].FirstOrDefault();
        bool stagedRequest = stagedProbe is not null;
        if (stagedRequest)
        {
            _ = TryResolveGenerationId(context.Request.Path, out string? requestedGenerationId);
            if (!promotions.TryCaptureStageProbe(
                    stagedProbe,
                    requestedGenerationId,
                    out ReleaseShelfSnapshot? stagedSnapshot)
                || stagedSnapshot is null)
            {
                context.Response.StatusCode = StatusCodes.Status404NotFound;
                ApplyStagedProbeNoStore(context.Response.Headers);
                return;
            }

            shelfStore.PinForCurrentRequest(stagedSnapshot);
            context.Response.OnStarting(() =>
            {
                ApplyStagedProbeNoStore(context.Response.Headers);
                return Task.CompletedTask;
            });
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
            if (IsReleaseAuthorityRequiredHandoffRoute(context.Request.Path))
            {
                context.Response.StatusCode = StatusCodes.Status503ServiceUnavailable;
                context.Response.ContentType = "application/json; charset=utf-8";
                context.Response.Headers["Cache-Control"] = "private, no-store, max-age=0";
                if (!HttpMethods.IsHead(context.Request.Method))
                {
                    await context.Response.WriteAsync(JsonSerializer.Serialize(new
                    {
                        status = "release_truth_unavailable",
                        message = "This handoff is withheld because immutable release authority could not be verified."
                    }, JsonOptions));
                }
                return;
            }

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
        if (!projection.AvailabilityClaimsAllowed
            && IsReleaseArtifactHandoffRoute(context.Request.Path))
        {
            context.Response.StatusCode = StatusCodes.Status409Conflict;
            context.Response.ContentType = "application/json; charset=utf-8";
            context.Response.Headers["Cache-Control"] = "private, no-store, max-age=0";
            if (!HttpMethods.IsHead(context.Request.Method))
            {
                await context.Response.WriteAsync(JsonSerializer.Serialize(new
                {
                    status = "review_required",
                    message = "This installer or updater handoff is withheld until immutable release authority allows availability claims.",
                    releaseTruth = projection
                }, JsonOptions));
            }
            return;
        }
        await _next(context);
    }

    private static void ApplyStagedProbeNoStore(IHeaderDictionary headers)
    {
        headers["Cache-Control"] = "private, no-store, no-cache, max-age=0";
        headers["CDN-Cache-Control"] = "no-store";
        headers["Cloudflare-CDN-Cache-Control"] = "no-store";
        headers["Surrogate-Control"] = "no-store";
        headers["Pragma"] = "no-cache";
        headers["Expires"] = "0";
        headers["Referrer-Policy"] = "no-referrer";
        headers["X-Robots-Tag"] = "noindex, nofollow, noarchive";
        headers["Vary"] = StagedProbeHeaderName;
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
        string value = NormalizePath(path);
        if (value.Equals("/", StringComparison.OrdinalIgnoreCase)
            || value.Equals("/now", StringComparison.OrdinalIgnoreCase)
            || value.Equals("/changelog", StringComparison.OrdinalIgnoreCase)
            || value.Equals("/downloads", StringComparison.OrdinalIgnoreCase)
            || value.Equals("/status", StringComparison.OrdinalIgnoreCase)
            || value.Equals("/artifacts", StringComparison.OrdinalIgnoreCase)
            || value.Equals("/progress", StringComparison.OrdinalIgnoreCase)
            || value.Equals("/help", StringComparison.OrdinalIgnoreCase)
            || value.Equals("/downloads/concierge", StringComparison.OrdinalIgnoreCase)
            || value.Equals("/now/concierge", StringComparison.OrdinalIgnoreCase))
        {
            return true;
        }

        return value.StartsWith("/downloads/", StringComparison.OrdinalIgnoreCase)
            || IsPersonalizedInstallScript(value)
            || value.StartsWith("/now/concierge/", StringComparison.OrdinalIgnoreCase)
            || value.Equals("/api/v1/install-linking/continuation", StringComparison.OrdinalIgnoreCase)
            || value.StartsWith("/api/v1/install-linking/continuation/", StringComparison.OrdinalIgnoreCase)
            || value.StartsWith("/api/v1/public/progress", StringComparison.OrdinalIgnoreCase)
            || value.StartsWith("/api/public/progress", StringComparison.OrdinalIgnoreCase)
            || value.Equals("/api/v1/public/weekly-pulse", StringComparison.OrdinalIgnoreCase)
            || value.Equals("/api/public/weekly-pulse", StringComparison.OrdinalIgnoreCase)
            || value.Equals("/api/v1/public/release-truth", StringComparison.OrdinalIgnoreCase)
            || value.Equals("/api/public/release-truth", StringComparison.OrdinalIgnoreCase)
            || value.StartsWith("/api/v1/public/release-truth/g/", StringComparison.OrdinalIgnoreCase)
            || value.StartsWith("/api/public/release-truth/g/", StringComparison.OrdinalIgnoreCase);
    }

    internal static bool IsReleaseArtifactHandoffRoute(PathString path)
    {
        string value = NormalizePath(path);
        if (IsPersonalizedInstallScript(value)
            || IsWindowsProofArtifactHandoff(value))
        {
            return true;
        }
        if (value.StartsWith("/downloads/get/", StringComparison.OrdinalIgnoreCase)
            || value.StartsWith("/downloads/file/", StringComparison.OrdinalIgnoreCase)
            || value.StartsWith("/downloads/files/", StringComparison.OrdinalIgnoreCase)
            || value.StartsWith("/downloads/install/", StringComparison.OrdinalIgnoreCase))
        {
            return true;
        }

        if (!value.StartsWith("/downloads/g/", StringComparison.OrdinalIgnoreCase))
        {
            return false;
        }

        string generationRemainder = value["/downloads/g/".Length..];
        int separator = generationRemainder.IndexOf('/');
        if (separator < 0)
        {
            return false;
        }

        string retainedPath = generationRemainder[separator..];
        return retainedPath.StartsWith("/install/", StringComparison.OrdinalIgnoreCase)
            || retainedPath.StartsWith("/files/", StringComparison.OrdinalIgnoreCase);
    }

    internal static bool IsReleaseAuthorityRequiredHandoffRoute(PathString path)
    {
        if (IsReleaseArtifactHandoffRoute(path))
        {
            return true;
        }

        string value = NormalizePath(path);
        return value.StartsWith("/downloads/concierge/", StringComparison.OrdinalIgnoreCase)
            || value.StartsWith("/now/concierge/", StringComparison.OrdinalIgnoreCase)
            || value.Equals("/api/v1/install-linking/continuation", StringComparison.OrdinalIgnoreCase)
            || value.StartsWith("/api/v1/install-linking/continuation/", StringComparison.OrdinalIgnoreCase);
    }

    private static bool IsPersonalizedInstallScript(string value)
        => value.StartsWith("/install-", StringComparison.OrdinalIgnoreCase)
           && value.EndsWith(".sh", StringComparison.OrdinalIgnoreCase)
           && value.Length > "/install-.sh".Length;

    private static bool IsWindowsProofArtifactHandoff(string value)
    {
        const string prefix = "/downloads/proof/windows/";
        if (!value.StartsWith(prefix, StringComparison.OrdinalIgnoreCase))
        {
            return false;
        }

        string remainder = value[prefix.Length..];
        if (remainder.Length == 0
            || remainder.Equals("current", StringComparison.OrdinalIgnoreCase)
            || remainder.Equals("upload", StringComparison.OrdinalIgnoreCase)
            || remainder.Equals("upload-ticket", StringComparison.OrdinalIgnoreCase))
        {
            return false;
        }

        string[] segments = remainder.Split('/', StringSplitOptions.RemoveEmptyEntries);
        if (segments.Length == 1)
        {
            return true;
        }
        if ((segments[0].Equals("generations", StringComparison.OrdinalIgnoreCase)
             || segments[0].Equals("candidates", StringComparison.OrdinalIgnoreCase))
            && segments.Length == 2)
        {
            return false;
        }

        return remainder.Contains("/files/", StringComparison.OrdinalIgnoreCase)
            || remainder.Contains("/installers/", StringComparison.OrdinalIgnoreCase)
            || segments[^1].Equals("installer", StringComparison.OrdinalIgnoreCase)
            || segments[^1].Equals("payload", StringComparison.OrdinalIgnoreCase)
            || segments[^1].Equals("metadata", StringComparison.OrdinalIgnoreCase);
    }

    private static bool TryResolveGenerationId(PathString path, out string? generationId)
    {
        string value = NormalizePath(path);
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

    private static string NormalizePath(PathString path)
    {
        string value = path.Value ?? string.Empty;
        return value.Length > 1 ? value.TrimEnd('/') : value;
    }

    private static string ToBase64Url(byte[] bytes)
        => Convert.ToBase64String(bytes)
            .TrimEnd('=')
            .Replace('+', '-')
            .Replace('/', '_');
}
