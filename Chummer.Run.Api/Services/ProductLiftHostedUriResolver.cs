namespace Chummer.Run.Api.Services;

internal static class ProductLiftHostedUriResolver
{
    private static readonly HashSet<string> RootEquivalentPaths = new(StringComparer.OrdinalIgnoreCase)
    {
        "/",
        "/feedback",
        "/feedback/",
        "/roadmap",
        "/roadmap/",
        "/changelog",
        "/changelog/",
        "/posts",
        "/posts/",
        "/board",
        "/board/"
    };

    public static Uri? TryResolve(string? configured)
    {
        if (string.IsNullOrWhiteSpace(configured)
            || !Uri.TryCreate(configured, UriKind.Absolute, out Uri? uri)
            || (uri.Scheme != Uri.UriSchemeHttps
                && !(uri.Scheme == Uri.UriSchemeHttp && uri.IsLoopback)))
        {
            return null;
        }

        return NormalizeProductLiftRoot(uri);
    }

    private static Uri NormalizeProductLiftRoot(Uri uri)
    {
        if (!IsProductLiftHost(uri.Host))
        {
            return uri;
        }

        string path = string.IsNullOrWhiteSpace(uri.AbsolutePath) ? "/" : uri.AbsolutePath;
        if (!RootEquivalentPaths.Contains(path))
        {
            return uri;
        }

        return new Uri($"{uri.GetLeftPart(UriPartial.Authority).TrimEnd('/')}/");
    }

    private static bool IsProductLiftHost(string host)
        => string.Equals(host, "productlift.dev", StringComparison.OrdinalIgnoreCase)
            || host.EndsWith(".productlift.dev", StringComparison.OrdinalIgnoreCase);
}
