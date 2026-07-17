using Chummer.Run.Api.Services;
using Microsoft.Extensions.Configuration;
using Xunit;

namespace Chummer.Tests;

public sealed class PublicCanonFileLoaderTests
{
    [Fact]
    public void LoadRequiredTextFallsBackToDesignMirrorForProductsChummerPaths()
    {
        string root = Path.Combine(Path.GetTempPath(), "public-canon-loader-tests", Guid.NewGuid().ToString("N"));
        try
        {
            string mirrorRoot = Path.Combine(root, ".codex-design", "product");
            Directory.CreateDirectory(mirrorRoot);
            File.WriteAllText(Path.Combine(mirrorRoot, "PUBLIC_FEEDBACK_TAXONOMY.yaml"), "version: 1\n");

            IConfiguration configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_PUBLIC_CANON_ROOT"] = root
                })
                .Build();

            PublicCanonFileLoader loader = new(configuration);

            string content = loader.LoadRequiredText("products/chummer/PUBLIC_FEEDBACK_TAXONOMY.yaml");

            Assert.Contains("version: 1", content, StringComparison.Ordinal);
            Assert.Equal(root, loader.ResolveRepoRoot("products/chummer/PUBLIC_FEEDBACK_TAXONOMY.yaml"));
            Assert.EndsWith(
                Path.Combine(".codex-design", "product", "PUBLIC_FEEDBACK_TAXONOMY.yaml"),
                loader.ResolveRequiredPath("products/chummer/PUBLIC_FEEDBACK_TAXONOMY.yaml"),
                StringComparison.Ordinal);
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
    public void LoadRequiredTextFallsBackToProductsChummerPathForMirrorPaths()
    {
        string root = Path.Combine(Path.GetTempPath(), "public-canon-loader-tests", Guid.NewGuid().ToString("N"));
        try
        {
            string productRoot = Path.Combine(root, "products", "chummer");
            Directory.CreateDirectory(productRoot);
            File.WriteAllText(Path.Combine(productRoot, "PUBLIC_PROGRESS_PARTS.yaml"), "version: 2\n");

            IConfiguration configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_PUBLIC_CANON_ROOT"] = root
                })
                .Build();

            PublicCanonFileLoader loader = new(configuration);

            string content = loader.LoadRequiredText(".codex-design/product/PUBLIC_PROGRESS_PARTS.yaml");

            Assert.Contains("version: 2", content, StringComparison.Ordinal);
            Assert.Equal(root, loader.ResolveRepoRoot(".codex-design/product/PUBLIC_PROGRESS_PARTS.yaml"));
            Assert.EndsWith(
                Path.Combine("products", "chummer", "PUBLIC_PROGRESS_PARTS.yaml"),
                loader.ResolveRequiredPath(".codex-design/product/PUBLIC_PROGRESS_PARTS.yaml"),
                StringComparison.Ordinal);
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
