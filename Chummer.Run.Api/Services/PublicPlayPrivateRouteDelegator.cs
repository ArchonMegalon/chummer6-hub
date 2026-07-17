using Microsoft.AspNetCore.Http;

namespace Chummer.Run.Api.Services;

public interface IPublicPlayPrivateRouteDelegator
{
    Task DenyAsync(HttpContext context, CancellationToken cancellationToken);
}

/// <summary>
/// Typed transport seam for a future server-to-server Play grant bridge. No private
/// HTTP or WebSocket route is delegated until that bridge has authoritative grants.
/// </summary>
public sealed class DenyAllPublicPlayPrivateRouteDelegator : IPublicPlayPrivateRouteDelegator
{
    public Task DenyAsync(HttpContext context, CancellationToken cancellationToken)
        => PublicPlayPrivateRouteResponse.WriteUnavailableAsync(context, cancellationToken);
}

public static class PublicPlayPrivateRouteResponse
{
    public static async Task WriteUnavailableAsync(HttpContext context, CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(context);

        context.Response.StatusCode = StatusCodes.Status404NotFound;
        context.Response.Headers.CacheControl = "private, no-store";
        context.Response.Headers.Pragma = "no-cache";
        context.Response.Headers.Expires = "0";
        context.Response.Headers["Referrer-Policy"] = "no-referrer";
        context.Response.Headers["X-Content-Type-Options"] = "nosniff";

        if (HttpMethods.IsHead(context.Request.Method))
        {
            return;
        }

        await context.Response.WriteAsJsonAsync(
            new
            {
                error = "play_session_unavailable",
                detail = "This live Play session is not available from this browser. Sign in and join through a trusted session invitation."
            },
            cancellationToken).ConfigureAwait(false);
    }
}
