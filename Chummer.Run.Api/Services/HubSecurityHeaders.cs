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

        headers["Content-Security-Policy"] = ContentSecurityPolicy;
        headers["Cross-Origin-Opener-Policy"] = "same-origin-allow-popups";
        headers["Permissions-Policy"] = PermissionsPolicy;
        headers["Referrer-Policy"] = "strict-origin-when-cross-origin";
        headers["Strict-Transport-Security"] = "max-age=31536000";
        headers["X-Content-Type-Options"] = "nosniff";
        headers["X-Frame-Options"] = "DENY";
        headers["X-Permitted-Cross-Domain-Policies"] = "none";
    }
}
