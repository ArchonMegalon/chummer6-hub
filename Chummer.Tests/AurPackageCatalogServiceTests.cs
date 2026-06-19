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
}
