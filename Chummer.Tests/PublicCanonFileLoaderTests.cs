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
                    ["CHUMMER_PUBLIC_CANON_ROOT"] = root,
                    ["CHUMMER_PUBLIC_STRICT_CONFIGURED_ROOT"] = "true"
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

    [Fact]
    public void StrictConfiguredRootDoesNotFallBackWhenRequiredFileIsMissing()
    {
        string root = CreateTestRoot();
        try
        {
            PublicCanonFileLoader loader = new(CreateStrictConfiguration(root));

            Assert.Throws<DirectoryNotFoundException>(() =>
                loader.ResolveRequiredPath("products/chummer/PUBLIC_FEEDBACK_TAXONOMY.yaml"));
        }
        finally
        {
            DeleteTestRoot(root);
        }
    }

    [Fact]
    public void StrictConfiguredRootRejectsRelativeConfiguredRoot()
    {
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_PUBLIC_CANON_ROOT"] = "relative-canon-root",
                ["CHUMMER_PUBLIC_STRICT_CONFIGURED_ROOT"] = "true"
            })
            .Build();
        PublicCanonFileLoader loader = new(configuration);

        InvalidOperationException exception = Assert.Throws<InvalidOperationException>(() =>
            loader.ResolveRequiredPath("products/chummer/PUBLIC_FEEDBACK_TAXONOMY.yaml"));

        Assert.Contains("absolute path", exception.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void StrictConfiguredRootRequiresConfiguredCanonRoot()
    {
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_PUBLIC_STRICT_CONFIGURED_ROOT"] = "true"
            })
            .Build();
        PublicCanonFileLoader loader = new(configuration);

        InvalidOperationException exception = Assert.Throws<InvalidOperationException>(() =>
            loader.ResolveRequiredPath("products/chummer/PUBLIC_FEEDBACK_TAXONOMY.yaml"));

        Assert.Contains("requires CHUMMER_PUBLIC_CANON_ROOT", exception.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void StrictConfiguredRootRejectsTraversalOutsideConfiguredRoot()
    {
        string testRoot = CreateTestRoot();
        string configuredRoot = Path.Combine(testRoot, "configured");
        Directory.CreateDirectory(configuredRoot);
        File.WriteAllText(Path.Combine(testRoot, "outside.yaml"), "outside: true\n");
        try
        {
            PublicCanonFileLoader loader = new(CreateStrictConfiguration(configuredRoot));

            InvalidOperationException exception = Assert.Throws<InvalidOperationException>(() =>
                loader.ResolveRequiredPath("../outside.yaml"));

            Assert.Contains("escapes", exception.Message, StringComparison.Ordinal);
        }
        finally
        {
            DeleteTestRoot(testRoot);
        }
    }

    [Fact]
    public void StrictConfiguredRootRejectsSymbolicLinkToOutsideFile()
    {
        if (OperatingSystem.IsWindows())
        {
            return;
        }

        string testRoot = CreateTestRoot();
        string configuredRoot = Path.Combine(testRoot, "configured");
        string productRoot = Path.Combine(configuredRoot, "products", "chummer");
        Directory.CreateDirectory(productRoot);
        string outsidePath = Path.Combine(testRoot, "outside.yaml");
        File.WriteAllText(outsidePath, "outside: true\n");
        File.CreateSymbolicLink(Path.Combine(productRoot, "linked.yaml"), outsidePath);
        try
        {
            PublicCanonFileLoader loader = new(CreateStrictConfiguration(configuredRoot));

            InvalidOperationException exception = Assert.Throws<InvalidOperationException>(() =>
                loader.ResolveRequiredPath("products/chummer/linked.yaml"));

            Assert.Contains("symbolic link or reparse point", exception.Message, StringComparison.Ordinal);
        }
        finally
        {
            DeleteTestRoot(testRoot);
        }
    }

    private static IConfiguration CreateStrictConfiguration(string root)
        => new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_PUBLIC_CANON_ROOT"] = root,
                ["CHUMMER_PUBLIC_STRICT_CONFIGURED_ROOT"] = "true"
            })
            .Build();

    private static string CreateTestRoot()
    {
        string root = Path.Combine(Path.GetTempPath(), "public-canon-loader-tests", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        return root;
    }

    private static void DeleteTestRoot(string root)
    {
        if (Directory.Exists(root))
        {
            Directory.Delete(root, recursive: true);
        }
    }
}
