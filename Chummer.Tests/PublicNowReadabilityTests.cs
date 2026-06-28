using System.Globalization;
using Xunit;

namespace Chummer.Tests;

public sealed class PublicNowReadabilityTests
{
    [Fact]
    public void Now_surface_tokens_keep_text_readable_against_declared_backgrounds()
    {
        string css = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "wwwroot", "css", "site.css"));

        Assert.Contains(".surface-now .status-decision-strip__card,", css, StringComparison.Ordinal);
        Assert.Contains("background: #fff9f1;", css, StringComparison.Ordinal);
        Assert.Contains(".surface-now .status-decision-strip__card p,", css, StringComparison.Ordinal);
        Assert.Contains("color: #43566f;", css, StringComparison.Ordinal);
        Assert.Contains(".surface-now .status-decision-strip__card h2,", css, StringComparison.Ordinal);
        Assert.Contains("color: #13233a;", css, StringComparison.Ordinal);

        Assert.True(ContrastRatio("#43566f", "#fff9f1") >= 7.0, "Current release body copy must stay readable on its card background.");
        Assert.True(ContrastRatio("#13233a", "#fff9f1") >= 12.0, "Current release headings must stay strongly readable on their card background.");
        Assert.True(ContrastRatio("#8b4f12", "#fff9f1") >= 5.0, "Current release eyebrow and tag color must stay readable on the light surface.");
    }

    private static double ContrastRatio(string foregroundHex, string backgroundHex)
    {
        double foreground = RelativeLuminance(foregroundHex);
        double background = RelativeLuminance(backgroundHex);
        double lighter = Math.Max(foreground, background);
        double darker = Math.Min(foreground, background);
        return (lighter + 0.05) / (darker + 0.05);
    }

    private static double RelativeLuminance(string hex)
    {
        (double r, double g, double b) = ParseHex(hex);
        return 0.2126 * Channel(r) + 0.7152 * Channel(g) + 0.0722 * Channel(b);
    }

    private static (double R, double G, double B) ParseHex(string hex)
    {
        string clean = hex.Replace("#", string.Empty, StringComparison.Ordinal).Trim();
        if (clean.Length != 6)
        {
            throw new ArgumentException($"Expected 6-digit hex color, got '{hex}'.");
        }

        return (
            ParsePair(clean[..2]),
            ParsePair(clean[2..4]),
            ParsePair(clean[4..6]));
    }

    private static double ParsePair(string pair)
        => int.Parse(pair, NumberStyles.HexNumber, CultureInfo.InvariantCulture) / 255d;

    private static double Channel(double value)
        => value <= 0.03928 ? value / 12.92 : Math.Pow((value + 0.055) / 1.055, 2.4);
}
