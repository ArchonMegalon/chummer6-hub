using System.Text.Json;
using Microsoft.AspNetCore.Mvc;

namespace Chummer.Run.Api.Controllers;

[ApiController]
public sealed class DownloadsCompatibilityController : ControllerBase
{
    private const string DefaultRoot = "/downloads-source";

    [HttpGet("/downloads/releases.json")]
    public IActionResult ReleaseManifest()
    {
        var root = ResolveDownloadsRoot();
        var manifestPath = Path.Combine(root, "releases.json");
        if (!System.IO.File.Exists(manifestPath))
        {
            return NotFound();
        }

        var manifest = LoadReleaseManifest(manifestPath);
        return Ok(manifest);
    }

    [HttpGet("/downloads/files/{**path}")]
    public IActionResult DownloadFile([FromRoute] string? path)
    {
        var filePath = ResolveDownloadFilePath(path);
        if (filePath is null)
        {
            return NotFound();
        }

        return PhysicalFile(filePath, "application/octet-stream", enableRangeProcessing: true);
    }

    private static string ResolveDownloadsRoot()
        => Environment.GetEnvironmentVariable("CHUMMER_DOWNLOADS_SOURCE_ROOT")?.Trim() is { Length: > 0 } configured
            ? configured
            : DefaultRoot;

    private static DownloadReleaseManifest LoadReleaseManifest(string manifestPath)
    {
        var options = new JsonSerializerOptions(JsonSerializerDefaults.Web)
        {
            PropertyNameCaseInsensitive = true
        };

        var json = System.IO.File.ReadAllText(manifestPath);
        var parsed = JsonSerializer.Deserialize<DownloadReleaseManifest>(json, options);
        if (parsed is null)
        {
            return new DownloadReleaseManifest(
                Version: "unpublished",
                Channel: "preview",
                PublishedAt: DateTimeOffset.UtcNow,
                Downloads: [],
                Source: "manifest",
                Status: "manifest-error",
                Message: "Release manifest exists but could not be parsed.",
                HasFallbackSource: false);
        }

        var status = parsed.Downloads.Count > 0
            ? "published"
            : string.Equals(parsed.Version, "unpublished", StringComparison.OrdinalIgnoreCase)
                ? "unpublished"
                : "manifest-empty";
        var message = parsed.Downloads.Count > 0
            ? null
            : status == "unpublished"
                ? "No published desktop builds are available yet."
                : "Release manifest is present but contains no downloadable artifacts.";
        return parsed with
        {
            Source = "manifest",
            Status = status,
            Message = message,
            HasFallbackSource = false
        };
    }

    private static string? ResolveDownloadFilePath(string? path)
    {
        if (string.IsNullOrWhiteSpace(path))
        {
            return null;
        }

        var root = Path.GetFullPath(ResolveDownloadsRoot());
        var relative = path.Trim().TrimStart('/').Replace('\\', '/');
        if (relative.Contains("..", StringComparison.Ordinal))
        {
            return null;
        }

        var candidate = Path.GetFullPath(Path.Combine(root, "files", relative.Replace('/', Path.DirectorySeparatorChar)));
        if (!candidate.StartsWith(root, StringComparison.Ordinal) || !System.IO.File.Exists(candidate))
        {
            return null;
        }

        return candidate;
    }

    private sealed record DownloadReleaseManifest(
        string Version,
        string Channel,
        DateTimeOffset PublishedAt,
        IReadOnlyList<DownloadArtifact> Downloads,
        string Source = "manifest",
        string Status = "published",
        string? Message = null,
        bool HasFallbackSource = false);

    private sealed record DownloadArtifact(
        string Id,
        string Platform,
        string Url,
        string Sha256,
        long? SizeBytes = null);
}
