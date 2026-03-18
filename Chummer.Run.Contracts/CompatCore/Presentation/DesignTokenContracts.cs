namespace Chummer.Contracts.Presentation;

public static class ThemeModes
{
    public const string System = "system";
    public const string Light = "light";
    public const string Dark = "dark";
}

public static class TypographyScales
{
    public const string Compact = "compact";
    public const string Default = "default";
    public const string Large = "large";
    public const string ExtraLarge = "extra-large";
}

public static class DensityModes
{
    public const string Compact = "compact";
    public const string Comfortable = "comfortable";
    public const string Spacious = "spacious";
}

public static class ContrastModes
{
    public const string Standard = "standard";
    public const string High = "high";
}

public static class TouchTargetModes
{
    public const string Default = "default";
    public const string Large = "large";
}

public sealed record DesignTokenSet(
    string Theme,
    string TypographyScale,
    string Density,
    string Contrast,
    string TouchTargetSize);
