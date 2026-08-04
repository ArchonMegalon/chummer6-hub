using Microsoft.AspNetCore.Http;

namespace Chummer.Run.Api;

internal static class PrivateResponseCacheHeaders
{
    internal static bool IsPrivateAccountSurface(PathString path)
        => path.StartsWithSegments("/account", StringComparison.OrdinalIgnoreCase)
           || path.StartsWithSegments("/api/v1/accounts", StringComparison.OrdinalIgnoreCase);

    internal static bool IsPrivateAdminSurface(PathString path)
        => path.StartsWithSegments("/admin", StringComparison.OrdinalIgnoreCase);

    internal static void Apply(IHeaderDictionary headers)
    {
        bool preserveNoCache = headers["Cache-Control"]
            .ToString()
            .Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)
            .Any(static token => string.Equals(token, "no-cache", StringComparison.OrdinalIgnoreCase));
        headers["Cache-Control"] = preserveNoCache
            ? "private, no-store, no-cache, max-age=0"
            : "private, no-store, max-age=0";
        headers["CDN-Cache-Control"] = "no-store, max-age=0";
        headers["Cloudflare-CDN-Cache-Control"] = "no-store, max-age=0";
        headers["Surrogate-Control"] = "no-store";
        headers["Pragma"] = "no-cache";
        headers["Expires"] = "0";
    }
}
