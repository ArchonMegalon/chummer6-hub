namespace Chummer.Tests;

internal static class RepoPaths
{
    public static string Root { get; } = Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "..", "..", "..", ".."));

    public static string FromRoot(params string[] segments)
        => Path.Combine(new[] { Root }.Concat(segments).ToArray());
}
