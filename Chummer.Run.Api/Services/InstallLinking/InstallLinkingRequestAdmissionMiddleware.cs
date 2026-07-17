namespace Chummer.Run.Api.Services.InstallLinking;

public sealed class InstallLinkingRequestAdmissionMiddleware(RequestDelegate next)
{
    private const string UnavailableMessage = "Install-linking is temporarily unavailable.";

    public async Task InvokeAsync(
        HttpContext context,
        IInstallLinkingStoreReadinessProbe readinessProbe)
    {
        if (!RequiresDurableStore(context.Request.Path))
        {
            await next(context);
            return;
        }

        bool ready;
        try
        {
            ready = readinessProbe.Evaluate().Ready;
        }
        catch
        {
            ready = false;
        }

        if (ready)
        {
            await next(context);
            return;
        }

        context.Response.StatusCode = StatusCodes.Status503ServiceUnavailable;
        context.Response.ContentType = "application/problem+json; charset=utf-8";
        context.Response.Headers.CacheControl = "private, no-store, max-age=0";
        context.Response.Headers.Pragma = "no-cache";
        context.Response.Headers.Expires = "0";
        await context.Response.WriteAsJsonAsync(
            new
            {
                type = "https://chummer.run/problems/install-linking-unavailable",
                title = "Install-linking unavailable.",
                status = StatusCodes.Status503ServiceUnavailable,
                detail = UnavailableMessage
            },
            cancellationToken: context.RequestAborted);
    }

    internal static bool RequiresDurableStore(PathString path)
    {
        string value = path.Value ?? string.Empty;
        return path.StartsWithSegments("/api/v1/install-linking", StringComparison.OrdinalIgnoreCase)
            || path.Equals("/account/access/install-link", StringComparison.OrdinalIgnoreCase)
            || path.StartsWithSegments("/downloads/install", StringComparison.OrdinalIgnoreCase)
            || (value.StartsWith("/install-", StringComparison.OrdinalIgnoreCase)
                && value.EndsWith(".sh", StringComparison.OrdinalIgnoreCase));
    }
}
