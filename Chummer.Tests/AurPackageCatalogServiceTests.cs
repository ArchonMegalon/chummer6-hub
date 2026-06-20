using System.Text.Json;
using Chummer.Run.Api.Services;
using Microsoft.Extensions.Configuration;
using Xunit;

namespace Chummer.Tests;

public sealed class AurPackageCatalogServiceTests
{
    [Fact]
    public void LoadCatalogResolvesCurrentArchSidecarFiles()
    {
        string root = Path.Combine(Path.GetTempPath(), "chummer-aur-catalog-tests", Guid.NewGuid().ToString("N"));

        try
        {
            string downloadsRoot = Path.Combine(root, "downloads");
            string filesRoot = Path.Combine(downloadsRoot, "files");
            Directory.CreateDirectory(filesRoot);
            File.WriteAllText(Path.Combine(filesRoot, "chummer6-bin-aur-source.tar.gz"), "archive");
            File.WriteAllText(Path.Combine(filesRoot, "chummer6-bin.PKGBUILD"), "pkgbuild");
            File.WriteAllText(Path.Combine(filesRoot, "chummer6-bin.SRCINFO"), "srcinfo");
            File.WriteAllText(
                Path.Combine(downloadsRoot, "aur-packages.json"),
                JsonSerializer.Serialize(
                    new
                    {
                        packages = new[]
                        {
                            new
                            {
                                id = "chummer6-bin",
                                packageName = "chummer6-bin",
                                packageVersion = "20260619.101500",
                                title = "Arch / CachyOS",
                                summary = "AUR-compatible source package.",
                                platformLabel = "Arch / CachyOS",
                                installCommand = "makepkg -si",
                                sourceArchiveFileName = "chummer6-bin-aur-source.tar.gz",
                                sourceArchiveUrl = "https://chummer.run/downloads/files/chummer6-bin-aur-source.tar.gz",
                                sourceArchiveSha256 = new string('a', 64),
                                sourceArchiveSizeBytes = 7,
                                pkgbuildFileName = "chummer6-bin.PKGBUILD",
                                pkgbuildUrl = "https://chummer.run/downloads/files/chummer6-bin.PKGBUILD",
                                pkgbuildSha256 = new string('b', 64),
                                srcinfoFileName = "chummer6-bin.SRCINFO",
                                srcinfoUrl = "https://chummer.run/downloads/files/chummer6-bin.SRCINFO",
                                srcinfoSha256 = new string('c', 64),
                                upstreamArtifactId = "avalonia-linux-x64-installer",
                                upstreamArtifactFileName = "chummer-avalonia-linux-x64-installer.deb",
                                upstreamArtifactUrl = "https://chummer.run/downloads/files/chummer-avalonia-linux-x64-installer.deb",
                                upstreamArtifactSha256 = new string('d', 64),
                                upstreamArtifactSizeBytes = 42
                            }
                        }
                    }),
                encoding: System.Text.Encoding.UTF8);

            var configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_DOWNLOADS_SOURCE_ROOT"] = downloadsRoot
                })
                .Build();

            var service = new AurPackageCatalogService(configuration);

            var package = Assert.Single(service.LoadCatalog().Packages);
            Assert.Equal("chummer6-bin", package.PackageName);
            Assert.Equal(Path.Combine(filesRoot, "chummer6-bin.PKGBUILD"), service.ResolvePackageFilePath("chummer6-bin.PKGBUILD"));
            Assert.NotNull(service.FindByFileName("chummer6-bin-aur-source.tar.gz"));
            Assert.Null(service.ResolvePackageFilePath("../chummer6-bin.PKGBUILD"));
            Assert.Null(service.FindByFileName("chummer-avalonia-linux-x64-installer.deb"));
        }
        finally
        {
            if (Directory.Exists(root))
            {
                Directory.Delete(root, recursive: true);
            }
        }
    }

    [Fact]
    public void CheckedInCatalogReferencesExistingArchSidecarsWithMatchingHashes()
    {
        string downloadsRoot = RepoPaths.FromRoot("Chummer.Portal", "downloads");
        var configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_DOWNLOADS_SOURCE_ROOT"] = downloadsRoot
            })
            .Build();
        var service = new AurPackageCatalogService(configuration);

        var package = Assert.Single(service.LoadCatalog().Packages);

        Assert.Equal("chummer6-bin", package.PackageName);
        Assert.Equal("Arch / CachyOS", package.PlatformLabel);
        Assert.Contains("makepkg -si", package.InstallCommand, StringComparison.Ordinal);
        Assert.Equal("avalonia-linux-x64-installer", package.UpstreamArtifactId);
        Assert.StartsWith("https://chummer.run/downloads/files/", package.SourceArchiveUrl, StringComparison.Ordinal);
        Assert.StartsWith("https://chummer.run/downloads/files/", package.PkgbuildUrl, StringComparison.Ordinal);
        Assert.StartsWith("https://chummer.run/downloads/files/", package.SrcinfoUrl, StringComparison.Ordinal);
        Assert.StartsWith("https://chummer.run/downloads/files/", package.UpstreamArtifactUrl, StringComparison.Ordinal);
        AssertSha256Shape(package.SourceArchiveSha256);
        AssertSha256Shape(package.PkgbuildSha256);
        AssertSha256Shape(package.SrcinfoSha256);
        AssertSha256Shape(package.UpstreamArtifactSha256);

        AssertOptionalSidecarHash(service, package.SourceArchiveFileName, package.SourceArchiveSha256, package.SourceArchiveSizeBytes);
        string? pkgbuildPath = AssertOptionalSidecarHash(service, package.PkgbuildFileName, package.PkgbuildSha256, null);
        string? srcinfoPath = AssertOptionalSidecarHash(service, package.SrcinfoFileName, package.SrcinfoSha256, null);

        string upstreamPath = Path.Combine(downloadsRoot, "files", package.UpstreamArtifactFileName);
        if (File.Exists(upstreamPath))
        {
            Assert.Equal(package.UpstreamArtifactSha256, Sha256(upstreamPath));
            Assert.Equal(new FileInfo(upstreamPath).Length, package.UpstreamArtifactSizeBytes);
        }
        Assert.Null(service.ResolvePackageFilePath(package.UpstreamArtifactFileName));

        if (pkgbuildPath is not null)
        {
            string pkgbuild = File.ReadAllText(pkgbuildPath);
            Assert.Contains($"source_x86_64=('{package.UpstreamArtifactFileName}::{package.UpstreamArtifactUrl}')", pkgbuild, StringComparison.Ordinal);
            Assert.Contains($"sha256sums_x86_64=('{package.UpstreamArtifactSha256}')", pkgbuild, StringComparison.Ordinal);
        }
        if (srcinfoPath is not null)
        {
            string srcinfo = File.ReadAllText(srcinfoPath);
            Assert.Contains($"source_x86_64 = {package.UpstreamArtifactFileName}::{package.UpstreamArtifactUrl}", srcinfo, StringComparison.Ordinal);
            Assert.Contains($"sha256sums_x86_64 = {package.UpstreamArtifactSha256}", srcinfo, StringComparison.Ordinal);
        }
    }

    private static string? AssertOptionalSidecarHash(AurPackageCatalogService service, string fileName, string expectedSha256, long? expectedSize)
    {
        string? path = service.ResolvePackageFilePath(fileName);
        if (path is not null)
        {
            Assert.True(File.Exists(path), $"Missing AUR sidecar file: {path}");
            Assert.Equal(expectedSha256, Sha256(path));
            if (expectedSize is long size)
            {
                Assert.Equal(size, new FileInfo(path).Length);
            }
        }

        Assert.NotNull(service.FindByFileName(fileName));
        return path;
    }

    private static string Sha256(string path)
        => Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(File.ReadAllBytes(path))).ToLowerInvariant();

    private static void AssertSha256Shape(string value)
    {
        Assert.Equal(64, value.Length);
        Assert.All(value, character => Assert.True(Uri.IsHexDigit(character), $"Invalid SHA-256 character: {character}"));
    }
}
