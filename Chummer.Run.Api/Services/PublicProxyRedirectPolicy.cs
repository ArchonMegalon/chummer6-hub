using Microsoft.AspNetCore.Http;

namespace Chummer.Run.Api.Services;

internal static class PublicProxyRedirectPolicy
{
    public const string HttpClientName = "PublicBrowserSurfaceProxy";

    public static Uri? TryBuildPublicOrigin(string scheme, HostString host)
    {
        if ((!string.Equals(scheme, Uri.UriSchemeHttp, StringComparison.OrdinalIgnoreCase)
             && !string.Equals(scheme, Uri.UriSchemeHttps, StringComparison.OrdinalIgnoreCase))
            || !host.HasValue)
        {
            return null;
        }

        return Uri.TryCreate($"{scheme}://{host.Value}/", UriKind.Absolute, out Uri? origin)
            ? origin
            : null;
    }

    public static bool TryRewrite(
        Uri location,
        Uri upstream,
        Uri? publicOrigin,
        string localBasePath,
        string fallbackPath,
        out string redirectPath)
    {
        ArgumentNullException.ThrowIfNull(location);
        ArgumentNullException.ThrowIfNull(upstream);

        redirectPath = string.Empty;
        if (location.IsAbsoluteUri)
        {
            if (publicOrigin is not null && HasSameOrigin(location, publicOrigin))
            {
                return TryNormalizeLocalPath(string.Empty, location.PathAndQuery + location.Fragment, fallbackPath, out redirectPath);
            }

            if (!HasSameOrigin(location, upstream))
            {
                return false;
            }

            return TryNormalizeLocalPath(localBasePath, location.PathAndQuery + location.Fragment, fallbackPath, out redirectPath);
        }

        return TryNormalizeLocalPath(localBasePath, location.OriginalString, fallbackPath, out redirectPath);
    }

    private static bool HasSameOrigin(Uri left, Uri right)
        => Uri.Compare(
            left,
            right,
            UriComponents.SchemeAndServer,
            UriFormat.Unescaped,
            StringComparison.OrdinalIgnoreCase) == 0;

    private static bool TryNormalizeLocalPath(
        string localBasePath,
        string pathAndQuery,
        string fallbackPath,
        out string redirectPath)
    {
        redirectPath = string.Empty;
        string candidate = string.IsNullOrWhiteSpace(pathAndQuery) ? string.Empty : pathAndQuery.Trim();
        if (string.IsNullOrEmpty(candidate) || candidate == "/")
        {
            redirectPath = fallbackPath;
            return true;
        }

        if (candidate.StartsWith("//", StringComparison.Ordinal)
            || candidate.Contains('\\')
            || candidate.Any(char.IsControl))
        {
            return false;
        }

        if (!candidate.StartsWith("/", StringComparison.Ordinal))
        {
            candidate = "/" + candidate;
        }

        if (candidate.StartsWith("//", StringComparison.Ordinal))
        {
            return false;
        }

        string normalizedBasePath = string.IsNullOrWhiteSpace(localBasePath)
            ? string.Empty
            : "/" + localBasePath.Trim().Trim('/');
        if (string.IsNullOrEmpty(normalizedBasePath))
        {
            redirectPath = candidate;
            return true;
        }

        if (string.Equals(candidate, normalizedBasePath, StringComparison.OrdinalIgnoreCase)
            || candidate.StartsWith(normalizedBasePath + "/", StringComparison.OrdinalIgnoreCase)
            || candidate.StartsWith(normalizedBasePath + "?", StringComparison.OrdinalIgnoreCase)
            || candidate.StartsWith(normalizedBasePath + "#", StringComparison.OrdinalIgnoreCase))
        {
            redirectPath = candidate;
            return true;
        }

        redirectPath = normalizedBasePath + candidate;
        return true;
    }
}
