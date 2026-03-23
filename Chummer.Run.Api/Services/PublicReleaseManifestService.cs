using System.Text.Json;
using Chummer.Run.Contracts.PublicSurface;

namespace Chummer.Run.Api.Services;

public sealed class PublicReleaseManifestService
{
    private const string DefaultRoot = "/downloads-source";
    private readonly IConfiguration _configuration;

    public PublicReleaseManifestService(IConfiguration configuration)
    {
        _configuration = configuration;
    }

    public PublicReleaseManifestDto LoadManifest()
    {
        var root = ResolveDownloadsRoot();
        var registryManifestPath = ResolveRegistryManifestPath(root);
        if (File.Exists(registryManifestPath))
        {
            return LoadRegistryReleaseManifest(registryManifestPath);
        }

        var manifestPath = Path.Combine(root, "releases.json");
        if (!File.Exists(manifestPath))
        {
            return new PublicReleaseManifestDto(
                Version: "unpublished",
                Channel: "preview",
                PublishedAt: DateTimeOffset.UtcNow,
                Downloads: [],
                Source: "fallback",
                Status: "unpublished",
                Message: "No published desktop builds are available yet.",
                HasFallbackSource: false);
        }

        return LoadReleaseManifest(manifestPath);
    }

    public string? ResolveDownloadFilePath(string? path)
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
        if (!candidate.StartsWith(root, StringComparison.Ordinal) || !File.Exists(candidate))
        {
            return null;
        }

        return candidate;
    }

    private string ResolveDownloadsRoot()
        => _configuration["CHUMMER_DOWNLOADS_SOURCE_ROOT"]?.Trim() is { Length: > 0 } configured
            ? configured
            : DefaultRoot;

    private string ResolveRegistryManifestPath(string downloadsRoot)
        => _configuration["CHUMMER_RELEASE_REGISTRY_MANIFEST_FILE"]?.Trim() is { Length: > 0 } configured
            ? configured
            : Path.Combine(downloadsRoot, "RELEASE_CHANNEL.generated.json");

    private static PublicReleaseManifestDto LoadReleaseManifest(string manifestPath)
    {
        var options = new JsonSerializerOptions(JsonSerializerDefaults.Web)
        {
            PropertyNameCaseInsensitive = true
        };

        var json = File.ReadAllText(manifestPath);
        var parsed = JsonSerializer.Deserialize<PublicReleaseManifestDto>(json, options);
        if (parsed is null)
        {
            return new PublicReleaseManifestDto(
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

    private static PublicReleaseManifestDto LoadRegistryReleaseManifest(string manifestPath)
    {
        var options = new JsonSerializerOptions(JsonSerializerDefaults.Web)
        {
            PropertyNameCaseInsensitive = true
        };

        var json = File.ReadAllText(manifestPath);
        var parsed = JsonSerializer.Deserialize<RegistryReleaseChannelManifest>(json, options);
        if (parsed is null)
        {
            return new PublicReleaseManifestDto(
                Version: "unpublished",
                Channel: "preview",
                PublishedAt: DateTimeOffset.UtcNow,
                Downloads: [],
                Source: "registry",
                Status: "manifest-error",
                Message: "Registry release manifest exists but could not be parsed.",
                HasFallbackSource: false);
        }

        var downloads = (parsed.Artifacts ?? [])
            .Where(item => !string.IsNullOrWhiteSpace(item.DownloadUrl))
            .Select(item => new PublicReleaseArtifactDto(
                Id: item.ArtifactId ?? item.FileName ?? "artifact",
                Platform: item.PlatformLabel ?? item.Platform ?? "Preview build",
                Url: item.DownloadUrl ?? "",
                Sha256: item.Sha256 ?? "",
                SizeBytes: item.SizeBytes))
            .ToList();

        var status = downloads.Count > 0
            ? "published"
            : string.Equals(parsed.Status, "manifest-empty", StringComparison.OrdinalIgnoreCase)
                ? "manifest-empty"
                : "unpublished";
        var message = downloads.Count > 0
            ? parsed.Message
            : status == "unpublished"
                ? "No published desktop builds are available yet."
                : "Registry release manifest is present but contains no downloadable artifacts.";

        return new PublicReleaseManifestDto(
            Version: parsed.Version ?? "unpublished",
            Channel: parsed.ChannelId ?? "preview",
            PublishedAt: parsed.PublishedAt ?? DateTimeOffset.UtcNow,
            Downloads: downloads,
            Source: "registry",
            Status: status,
            Message: message,
            HasFallbackSource: false);
    }

    private sealed record RegistryReleaseChannelManifest(
        string? Product,
        string? ChannelId,
        string? Version,
        DateTimeOffset? PublishedAt,
        string? Status,
        string? Message,
        IReadOnlyList<RegistryReleaseArtifact>? Artifacts);

    private sealed record RegistryReleaseArtifact(
        string? ArtifactId,
        string? Platform,
        string? PlatformLabel,
        string? FileName,
        string? DownloadUrl,
        string? Sha256,
        long? SizeBytes);
}
