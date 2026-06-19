using System.Text.Json;
using System.Text.Json.Serialization;

namespace Chummer.Run.Api.Services;

public sealed class AurPackageCatalogService
{
    private const string DownloadsRootKey = "CHUMMER_DOWNLOADS_SOURCE_ROOT";
    private const string PublicCanonRootKey = "CHUMMER_PUBLIC_CANON_ROOT";
    private const string DefaultRoot = "/downloads-source";
    private static readonly HashSet<string> DownloadableFileNames = new(StringComparer.OrdinalIgnoreCase)
    {
        "chummer6-bin-aur-source.tar.gz",
        "chummer6-bin.PKGBUILD",
        "chummer6-bin.SRCINFO"
    };

    private readonly IConfiguration _configuration;

    public AurPackageCatalogService(IConfiguration configuration)
    {
        _configuration = configuration;
    }

    public AurPackageCatalog LoadCatalog()
    {
        string catalogPath = Path.Combine(ResolveDownloadsRoot(), "aur-packages.json");
        if (!File.Exists(catalogPath))
        {
            return new AurPackageCatalog([]);
        }

        try
        {
            var payload = JsonSerializer.Deserialize<AurPackageCatalogDocument>(
                File.ReadAllText(catalogPath),
                new JsonSerializerOptions(JsonSerializerDefaults.Web));
            return new AurPackageCatalog((payload?.Packages ?? []).Where(IsComplete).ToArray());
        }
        catch (JsonException)
        {
            return new AurPackageCatalog([]);
        }
        catch (IOException)
        {
            return new AurPackageCatalog([]);
        }
    }

    public AurPackageEntry? FindByFileName(string? fileName)
    {
        string? normalized = NormalizeSidecarFileName(fileName);
        if (normalized is null)
        {
            return null;
        }

        return LoadCatalog().Packages.FirstOrDefault(package =>
            string.Equals(package.SourceArchiveFileName, normalized, StringComparison.OrdinalIgnoreCase)
            || string.Equals(package.PkgbuildFileName, normalized, StringComparison.OrdinalIgnoreCase)
            || string.Equals(package.SrcinfoFileName, normalized, StringComparison.OrdinalIgnoreCase));
    }

    public string? ResolvePackageFilePath(string? fileName)
    {
        string? normalized = NormalizeSidecarFileName(fileName);
        if (normalized is null)
        {
            return null;
        }

        string root = Path.GetFullPath(ResolveDownloadsRoot());
        string candidate = Path.GetFullPath(Path.Combine(root, "files", normalized));
        return candidate.StartsWith(root, StringComparison.Ordinal) && File.Exists(candidate)
            ? candidate
            : null;
    }

    private static string? NormalizeSidecarFileName(string? value)
    {
        string raw = (value ?? string.Empty).Trim();
        if (string.IsNullOrWhiteSpace(raw)
            || raw.Contains("..", StringComparison.Ordinal)
            || raw.Contains('/', StringComparison.Ordinal)
            || raw.Contains('\\', StringComparison.Ordinal))
        {
            return null;
        }

        string fileName = Path.GetFileName(raw);
        return DownloadableFileNames.Contains(fileName) ? fileName : null;
    }

    private static bool IsComplete(AurPackageEntry package)
        => !string.IsNullOrWhiteSpace(package.PackageName)
           && !string.IsNullOrWhiteSpace(package.SourceArchiveFileName)
           && !string.IsNullOrWhiteSpace(package.SourceArchiveUrl)
           && !string.IsNullOrWhiteSpace(package.SourceArchiveSha256)
           && !string.IsNullOrWhiteSpace(package.UpstreamArtifactSha256);

    private string ResolveDownloadsRoot()
    {
        if (_configuration[DownloadsRootKey]?.Trim() is { Length: > 0 } configured)
        {
            return configured;
        }

        foreach (string candidate in ResolveDefaultDownloadsRootCandidates())
        {
            if (Directory.Exists(candidate))
            {
                return candidate;
            }
        }

        return DefaultRoot;
    }

    private IEnumerable<string> ResolveDefaultDownloadsRootCandidates()
    {
        if (_configuration[PublicCanonRootKey]?.Trim() is { Length: > 0 } canonRoot)
        {
            yield return Path.Combine(canonRoot, "Chummer.Portal", "downloads");
        }

        foreach (string candidate in ResolveAncestorPortalDownloadsRoots(Directory.GetCurrentDirectory()))
        {
            yield return candidate;
        }

        foreach (string candidate in ResolveAncestorPortalDownloadsRoots(AppContext.BaseDirectory))
        {
            yield return candidate;
        }
    }

    private static IEnumerable<string> ResolveAncestorPortalDownloadsRoots(string start)
    {
        var cursor = new DirectoryInfo(Path.GetFullPath(start));
        while (cursor is not null)
        {
            yield return Path.Combine(cursor.FullName, "Chummer.Portal", "downloads");
            cursor = cursor.Parent;
        }
    }

    private sealed record AurPackageCatalogDocument(
        [property: JsonPropertyName("packages")] IReadOnlyList<AurPackageEntry>? Packages);
}

public sealed record AurPackageCatalog(IReadOnlyList<AurPackageEntry> Packages);

public sealed record AurPackageEntry(
    string Id,
    string PackageName,
    string PackageVersion,
    string Title,
    string Summary,
    string PlatformLabel,
    string InstallCommand,
    string SourceArchiveFileName,
    string SourceArchiveUrl,
    string SourceArchiveSha256,
    long? SourceArchiveSizeBytes,
    string PkgbuildFileName,
    string PkgbuildUrl,
    string PkgbuildSha256,
    string SrcinfoFileName,
    string SrcinfoUrl,
    string SrcinfoSha256,
    string UpstreamArtifactId,
    string UpstreamArtifactFileName,
    string UpstreamArtifactUrl,
    string UpstreamArtifactSha256,
    long? UpstreamArtifactSizeBytes);
