namespace Chummer.Run.Api.Services;

// Shared with the HTTP regression fixture so it exercises these production routes.
public static class PublicReleaseEvidenceDownloadEndpoints
{
    public static IEndpointRouteBuilder MapPublicReleaseEvidenceDownloads(this IEndpointRouteBuilder endpoints)
    {
        endpoints.MapGet("/downloads/release-evidence/{**path}", (
            string? path, PublicReleaseManifestService releases, HttpContext context) =>
            Serve(releases, context, null, $"release-evidence/{path}"));
        endpoints.MapGet("/downloads/g/{generationId}/release-evidence/{**path}", (
            string generationId, string? path, PublicReleaseManifestService releases, HttpContext context) =>
            Serve(releases, context, generationId, $"release-evidence/{path}"));
        endpoints.MapGet("/downloads/g/{generationId}/proof/{**path}", (
            string generationId, string? path, PublicReleaseManifestService releases, HttpContext context) =>
            Serve(releases, context, generationId, $"proof/{path}"));
        endpoints.MapGet("/downloads/g/{generationId}/startup-smoke/{**path}", (
            string generationId, string? path, PublicReleaseManifestService releases, HttpContext context) =>
            Serve(releases, context, generationId, $"startup-smoke/{path}"));
        return endpoints;
    }

    private static IResult Serve(PublicReleaseManifestService releases, HttpContext context,
        string? generationId, string relativePath)
    {
        // Also enforce the boundary if this endpoint is hosted without the projection middleware.
        if (PublicReleaseEvidenceDownloadPolicy.RejectRequest(context.Request)
            || PublicReleaseEvidenceDownloadPolicy.IsPrivateAuthorityPath(relativePath))
            return Results.NotFound();
        try
        {
            ReleaseShelfSnapshot snapshot = generationId is null
                ? releases.CaptureShelfSnapshot()
                : releases.CaptureShelfGeneration(generationId);
            if (!string.IsNullOrWhiteSpace(snapshot.GenerationId))
                context.Response.Headers["X-Chummer-Release-Generation"] = snapshot.GenerationId;
            return PublicReleaseEvidenceDownloadPolicy.Serve(snapshot, relativePath, releases, context);
        }
        catch (Exception exception) when (exception is InvalidDataException or InvalidOperationException)
        {
            return Results.NotFound();
        }
    }
}
