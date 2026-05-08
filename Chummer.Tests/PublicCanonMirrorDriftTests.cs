using Xunit;

namespace Chummer.Tests;

public sealed class PublicCanonMirrorDriftTests
{
    [Theory]
    [InlineData("PUBLIC_RELEASE_EXPERIENCE.yaml")]
    [InlineData("PUBLIC_LANDING_MANIFEST.yaml")]
    [InlineData("PUBLIC_FEATURE_REGISTRY.yaml")]
    [InlineData("PUBLIC_DOWNLOADS_POLICY.md")]
    [InlineData("PUBLIC_LANDING_POLICY.md")]
    [InlineData("horizons/black-ledger.md")]
    public void RunServicesPublicMirrorMatchesCanonicalChummerDesignSource(string relativePath)
    {
        string sourcePath = Path.Combine("/docker/chummercomplete/chummer-design/products/chummer", relativePath);
        string mirrorPath = RepoPaths.FromRoot(".codex-design", "product", relativePath);

        Assert.True(File.Exists(sourcePath), $"missing canonical source file: {sourcePath}");
        Assert.True(File.Exists(mirrorPath), $"missing run-services mirror file: {mirrorPath}");
        Assert.Equal(File.ReadAllText(sourcePath), File.ReadAllText(mirrorPath));
    }
}
