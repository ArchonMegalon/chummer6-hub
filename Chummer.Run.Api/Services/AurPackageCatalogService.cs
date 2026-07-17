using System.Text.Json;
using System.Text.Json.Serialization;
using System.Text;

namespace Chummer.Run.Api.Services;

public sealed class AurPackageCatalogService
{
    private static readonly HashSet<string> DownloadableFileNames = new(StringComparer.OrdinalIgnoreCase)
    {
        "chummer6-bin-aur-source.tar.gz",
        "chummer6-bin.PKGBUILD",
        "chummer6-bin.SRCINFO"
    };

    private readonly ReleaseShelfGenerationStore _shelfStore;

    public AurPackageCatalogService(IConfiguration configuration)
        : this(configuration, new ReleaseShelfGenerationStore(configuration))
    {
    }

    public AurPackageCatalogService(
        IConfiguration configuration,
        ReleaseShelfGenerationStore shelfStore)
    {
        ArgumentNullException.ThrowIfNull(configuration);
        _shelfStore = shelfStore ?? throw new ArgumentNullException(nameof(shelfStore));
    }

    public AurPackageCatalog LoadCatalog()
        => LoadCatalog(_shelfStore.CaptureForCurrentRequest());

    public AurPackageCatalog LoadCatalog(ReleaseShelfSnapshot snapshot)
    {
        ArgumentNullException.ThrowIfNull(snapshot);
        const string catalogRelativePath = "aur-packages.json";
        byte[]? catalogBytes = snapshot.IsLegacy
            ? ReadBoundedLegacyCatalog(snapshot.ResolveLegacyFilePath(catalogRelativePath))
            : snapshot.ReadVerifiedFileBytes(
                catalogRelativePath,
                ReleaseShelfGenerationStore.MaximumAurCatalogBytes);
        if (catalogBytes is null)
        {
            return new AurPackageCatalog([]);
        }

        try
        {
            var payload = JsonSerializer.Deserialize<AurPackageCatalogDocument>(
                catalogBytes,
                new JsonSerializerOptions(JsonSerializerDefaults.Web));
            IReadOnlyList<AurPackageEntry> packages = (payload?.Packages ?? [])
                .Where(IsComplete)
                .ToArray();
            if (snapshot.IsLegacy)
            {
                return new AurPackageCatalog(packages);
            }

            return new AurPackageCatalog(
                packages
                    .Select(package => ValidateAndBindGenerationPackage(snapshot, package))
                    .Where(static package => package is not null)
                    .Select(static package => package!)
                    .ToArray());
        }
        catch (JsonException)
        {
            return new AurPackageCatalog([]);
        }
        catch (IOException)
        {
            return new AurPackageCatalog([]);
        }
        catch (DecoderFallbackException)
        {
            return new AurPackageCatalog([]);
        }
    }

    public AurPackageEntry? FindByFileName(string? fileName)
        => FindByFileName(_shelfStore.CaptureForCurrentRequest(), fileName);

    public AurPackageEntry? FindByFileName(
        ReleaseShelfSnapshot snapshot,
        string? fileName)
    {
        ArgumentNullException.ThrowIfNull(snapshot);
        string? normalized = NormalizeSidecarFileName(fileName);
        if (normalized is null)
        {
            return null;
        }

        return LoadCatalog(snapshot).Packages.FirstOrDefault(package =>
            string.Equals(package.SourceArchiveFileName, normalized, StringComparison.OrdinalIgnoreCase)
            || string.Equals(package.PkgbuildFileName, normalized, StringComparison.OrdinalIgnoreCase)
            || string.Equals(package.SrcinfoFileName, normalized, StringComparison.OrdinalIgnoreCase));
    }

    public string? ResolvePackageFilePath(string? fileName)
        => ResolvePackageFilePath(_shelfStore.CaptureForCurrentRequest(), fileName);

    public string? ResolvePackageFilePath(
        ReleaseShelfSnapshot snapshot,
        string? fileName)
    {
        ArgumentNullException.ThrowIfNull(snapshot);
        string? normalized = NormalizeSidecarFileName(fileName);
        if (normalized is null)
        {
            return null;
        }

        return snapshot.IsLegacy
            ? snapshot.ResolveLegacyFilePath($"files/{normalized}")
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

    private static AurPackageEntry? ValidateAndBindGenerationPackage(
        ReleaseShelfSnapshot snapshot,
        AurPackageEntry package)
    {
        if (snapshot.GenerationId is not { Length: > 0 } generationId
            || !TryValidateGenerationFile(
                snapshot,
                package.SourceArchiveFileName,
                package.SourceArchiveUrl,
                package.SourceArchiveSha256,
                package.SourceArchiveSizeBytes,
                out ReleaseShelfInventoryEntry? sourceArchive)
            || !TryValidateGenerationFile(
                snapshot,
                package.PkgbuildFileName,
                package.PkgbuildUrl,
                package.PkgbuildSha256,
                expectedSize: null,
                out _)
            || !TryValidateGenerationFile(
                snapshot,
                package.SrcinfoFileName,
                package.SrcinfoUrl,
                package.SrcinfoSha256,
                expectedSize: null,
                out _)
            || !TryValidateGenerationFile(
                snapshot,
                package.UpstreamArtifactFileName,
                package.UpstreamArtifactUrl,
                package.UpstreamArtifactSha256,
                package.UpstreamArtifactSizeBytes,
                out ReleaseShelfInventoryEntry? upstream))
        {
            return null;
        }

        string prefix = $"/downloads/g/{generationId}/files/";
        return package with
        {
            SourceArchiveUrl = prefix + Uri.EscapeDataString(package.SourceArchiveFileName),
            SourceArchiveSizeBytes = sourceArchive!.SizeBytes,
            PkgbuildUrl = prefix + Uri.EscapeDataString(package.PkgbuildFileName),
            SrcinfoUrl = prefix + Uri.EscapeDataString(package.SrcinfoFileName),
            UpstreamArtifactUrl = prefix + Uri.EscapeDataString(package.UpstreamArtifactFileName),
            UpstreamArtifactSizeBytes = upstream!.SizeBytes
        };
    }

    private static bool TryValidateGenerationFile(
        ReleaseShelfSnapshot snapshot,
        string fileName,
        string sourceUrl,
        string expectedSha256,
        long? expectedSize,
        out ReleaseShelfInventoryEntry? inventoryEntry)
    {
        inventoryEntry = null;
        string normalizedFileName = (fileName ?? string.Empty).Trim();
        if (string.IsNullOrWhiteSpace(normalizedFileName)
            || normalizedFileName.Contains("..", StringComparison.Ordinal)
            || normalizedFileName.Contains('/', StringComparison.Ordinal)
            || normalizedFileName.Contains('\\', StringComparison.Ordinal)
            || !UrlRefersToFile(sourceUrl, normalizedFileName)
            || !snapshot.Inventory.TryGetValue($"files/{normalizedFileName}", out ReleaseShelfInventoryEntry? expected)
            || !string.Equals(expected.Sha256, expectedSha256?.Trim(), StringComparison.OrdinalIgnoreCase)
            || (expectedSize is long size && size != expected.SizeBytes))
        {
            return false;
        }

        inventoryEntry = expected;
        return true;
    }

    private static bool UrlRefersToFile(string sourceUrl, string fileName)
    {
        string raw = (sourceUrl ?? string.Empty).Trim();
        if (string.IsNullOrWhiteSpace(raw)
            || !Uri.TryCreate(raw, UriKind.RelativeOrAbsolute, out Uri? uri))
        {
            return false;
        }

        string path;
        if (uri.IsAbsoluteUri)
        {
            if (!string.IsNullOrEmpty(uri.Query) || !string.IsNullOrEmpty(uri.Fragment))
            {
                return false;
            }

            path = uri.AbsolutePath;
        }
        else
        {
            if (raw.Contains('?') || raw.Contains('#'))
            {
                return false;
            }

            path = raw;
        }

        return string.Equals(
            Path.GetFileName(Uri.UnescapeDataString(path)),
            fileName,
            StringComparison.Ordinal);
    }

    private static byte[]? ReadBoundedLegacyCatalog(string? path)
    {
        if (path is null)
        {
            return null;
        }

        try
        {
            using var stream = new FileStream(
                path,
                FileMode.Open,
                FileAccess.Read,
                FileShare.Read,
                bufferSize: 64 * 1024,
                FileOptions.SequentialScan);
            long descriptorLength = stream.Length;
            if (descriptorLength <= 0
                || descriptorLength > ReleaseShelfGenerationStore.MaximumAurCatalogBytes)
            {
                return null;
            }

            byte[] bytes = new byte[checked((int)descriptorLength)];
            stream.ReadExactly(bytes);
            if (stream.ReadByte() != -1 || stream.Length != descriptorLength)
            {
                return null;
            }

            _ = new UTF8Encoding(encoderShouldEmitUTF8Identifier: false, throwOnInvalidBytes: true)
                .GetString(bytes);
            return bytes;
        }
        catch (IOException)
        {
            return null;
        }
        catch (UnauthorizedAccessException)
        {
            return null;
        }
        catch (DecoderFallbackException)
        {
            return null;
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
