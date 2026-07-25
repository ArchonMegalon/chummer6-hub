using Microsoft.AspNetCore.Http;

namespace Chummer.Run.Api.Services;

public static class HubSecurityHeaders
{
    public const string ContentSecurityPolicy =
        "base-uri 'self'; frame-ancestors 'none'; object-src 'none'";

    public const string PermissionsPolicy =
        "camera=(), geolocation=(), microphone=(), payment=(), usb=()";

    public static void Apply(IHeaderDictionary headers)
    {
        ArgumentNullException.ThrowIfNull(headers);

        headers.TryAdd("Content-Security-Policy", ContentSecurityPolicy);
        headers.TryAdd("Cross-Origin-Opener-Policy", "same-origin-allow-popups");
        headers.TryAdd("Permissions-Policy", PermissionsPolicy);
        headers.TryAdd("Referrer-Policy", "strict-origin-when-cross-origin");
        headers.TryAdd("Strict-Transport-Security", "max-age=31536000");
        headers.TryAdd("X-Content-Type-Options", "nosniff");
        headers.TryAdd("X-Frame-Options", "DENY");
        headers.TryAdd("X-Permitted-Cross-Domain-Policies", "none");
    }
}
