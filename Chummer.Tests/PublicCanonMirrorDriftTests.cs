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
    [InlineData("PUBLIC_GUIDE_POLICY.md")]
    [InlineData("PUBLIC_GUIDE_EXPORT_MANIFEST.yaml")]
    [InlineData("PUBLIC_HELP_COPY.md")]
    [InlineData("WEEKLY_PRODUCT_PULSE.generated.json")]
    [InlineData("NEXT_90_DAY_PRODUCT_ADVANCE_REGISTRY.yaml")]
    [InlineData("NEXT_90_DAY_QUEUE_STAGING.generated.yaml")]
    [InlineData("horizons/black-ledger.md")]
    public void RunServicesPublicMirrorMatchesCanonicalChummerDesignSource(string relativePath)
    {
        string sourcePath = Path.Combine("/docker/chummercomplete/chummer-design/products/chummer", relativePath);
        string mirrorPath = RepoPaths.FromRoot(".codex-design", "product", relativePath);

        Assert.True(File.Exists(sourcePath), $"missing canonical source file: {sourcePath}");
        Assert.True(File.Exists(mirrorPath), $"missing run-services mirror file: {mirrorPath}");
        Assert.Equal(
            ReadCanonicalProductMirrorComparableText(sourcePath, relativePath),
            ReadCanonicalProductMirrorComparableText(mirrorPath, relativePath));
    }

    private static string ReadCanonicalProductMirrorComparableText(string path, string relativePath)
    {
        string text = File.ReadAllText(path);
        if (!string.Equals(relativePath, "WEEKLY_PRODUCT_PULSE.generated.json", StringComparison.Ordinal))
        {
            return text;
        }

        var payload = System.Text.Json.Nodes.JsonNode.Parse(text) as System.Text.Json.Nodes.JsonObject;
        Assert.NotNull(payload);
        payload["generated_at"] = "__normalized_generated_at__";
        return payload.ToJsonString(new System.Text.Json.JsonSerializerOptions { WriteIndented = true });
    }
}
