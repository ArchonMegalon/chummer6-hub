using System.Security.Cryptography;
using System.Text;
using Chummer.Run.Api.Services.InstallLinking;

namespace Chummer.Run.Api.Services.Community;

/// <summary>
/// Worker routes exist only on a separately configured local Docker listener.
/// Gate runs before forwarded headers and MVC/body binding. No shared EA token
/// fallback, browser session, install grant or public-listener access is accepted.
/// </summary>
public sealed class OriginChapterWorkerGateMiddleware(RequestDelegate next, IConfiguration configuration)
{
    public const string Prefix = "/api/internal/origin/chapters";
    private static readonly object Admitted = new();

    public async Task InvokeAsync(HttpContext context)
    {
        bool workerPath = context.Request.Path.StartsWithSegments(Prefix, StringComparison.OrdinalIgnoreCase);
        bool configured = int.TryParse(configuration["CHUMMER_ORIGIN_CHAPTER_WORKER_PORT"], out int port)
            && port is >= 1024 and <= 65535;
        bool workerListener = configured && context.Connection.LocalPort == port;
        if (!workerPath && !workerListener) { await next(context); return; }
        AndroidLinkedV2RequestProofMiddleware.ApplyPrivateResponseHeaders(context.Response.Headers);
        if (!workerPath || !workerListener) { context.Response.StatusCode = StatusCodes.Status404NotFound; return; }
        string? expected = configuration["CHUMMER_ORIGIN_CHAPTER_WORKER_TOKEN"];
        if (string.IsNullOrWhiteSpace(expected) || expected.Length is < 32 or > 256 || expected.Any(char.IsControl))
        { context.Response.StatusCode = StatusCodes.Status503ServiceUnavailable; return; }
        if (context.Request.Headers.Authorization.Count != 1)
        { context.Response.StatusCode = StatusCodes.Status401Unauthorized; return; }
        string provided = context.Request.Headers.Authorization.ToString();
        if (!provided.StartsWith("Bearer ", StringComparison.Ordinal) || provided.Length > 263
            || !CryptographicOperations.FixedTimeEquals(SHA256.HashData(Encoding.UTF8.GetBytes(provided[7..])),
                SHA256.HashData(Encoding.UTF8.GetBytes(expected))))
        { context.Response.StatusCode = StatusCodes.Status401Unauthorized; return; }
        if (context.Request.ContentLength > OriginChapterAuthoringService.MaximumRequestBytes * 2)
        { context.Response.StatusCode = StatusCodes.Status413PayloadTooLarge; return; }
        context.Items[Admitted] = true;
        await next(context);
    }

    internal static bool IsAdmitted(HttpContext context) => context.Items.TryGetValue(Admitted, out object? value) && value is true;
}

public static class OriginChapterWorkerPipeline
{
    public static IApplicationBuilder UseOriginChapterWorkerLane(this IApplicationBuilder app)
    {
        app.UseMiddleware<OriginChapterWorkerGateMiddleware>();
        // An authenticated local worker is not a public-site browser. Keep it
        // outside canonical-host redirects, HTTPS redirects and browser cookies.
        // The gate already rejected every non-worker path on this listener.
        app.MapWhen(OriginChapterWorkerGateMiddleware.IsAdmitted, worker =>
        {
            worker.UseRouting();
            worker.UseEndpoints(endpoints => endpoints.MapControllers());
        });
        return app;
    }
}
