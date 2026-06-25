namespace Chummer.Run.Api.Services;

public static class RybbitProxyPolicy
{
    private static readonly HashSet<string> AllowedRequestHeaders = new(StringComparer.OrdinalIgnoreCase)
    {
        "Accept",
        "Accept-Encoding",
        "Accept-Language",
        "Cache-Control",
        "Content-Type",
        "If-Modified-Since",
        "If-None-Match",
        "Origin",
        "Pragma",
        "Referer",
        "Sec-CH-UA",
        "Sec-CH-UA-Mobile",
        "Sec-CH-UA-Platform",
        "Sec-Fetch-Dest",
        "Sec-Fetch-Mode",
        "Sec-Fetch-Site",
        "User-Agent",
        "X-Requested-With"
    };

    private static readonly HashSet<string> BlockedRequestHeaders = new(StringComparer.OrdinalIgnoreCase)
    {
        "Authorization",
        "Connection",
        "Content-Length",
        "Cookie",
        "Forwarded",
        "Host",
        "Keep-Alive",
        "Proxy-Authorization",
        "TE",
        "Trailer",
        "Transfer-Encoding",
        "Upgrade",
        "Via",
        "X-Forwarded-For",
        "X-Forwarded-Host",
        "X-Forwarded-Proto"
    };

    private static readonly HashSet<string> AllowedResponseHeaders = new(StringComparer.OrdinalIgnoreCase)
    {
        "Access-Control-Allow-Headers",
        "Access-Control-Allow-Methods",
        "Access-Control-Allow-Origin",
        "Access-Control-Max-Age",
        "Allow",
        "Cache-Control",
        "Content-Encoding",
        "Content-Language",
        "Content-Length",
        "Content-Type",
        "ETag",
        "Expires",
        "Last-Modified",
        "Vary",
        "X-Content-Type-Options"
    };

    private static readonly HashSet<string> BlockedResponseHeaders = new(StringComparer.OrdinalIgnoreCase)
    {
        "Connection",
        "Keep-Alive",
        "Proxy-Authenticate",
        "Proxy-Authorization",
        "Set-Cookie",
        "TE",
        "Trailer",
        "Transfer-Encoding",
        "Upgrade",
        "Via"
    };

    public static bool ShouldForwardRequestHeader(string headerName)
    {
        if (string.IsNullOrWhiteSpace(headerName))
        {
            return false;
        }

        if (BlockedRequestHeaders.Contains(headerName))
        {
            return false;
        }

        return AllowedRequestHeaders.Contains(headerName);
    }

    public static bool ShouldForwardResponseHeader(string headerName)
    {
        if (string.IsNullOrWhiteSpace(headerName))
        {
            return false;
        }

        if (BlockedResponseHeaders.Contains(headerName))
        {
            return false;
        }

        return AllowedResponseHeaders.Contains(headerName);
    }

    public static string? NormalizeProxyPath(string proxyPath)
    {
        string normalized = (proxyPath ?? string.Empty).Replace('\\', '/').Trim('/');
        if (string.IsNullOrWhiteSpace(normalized))
        {
            return string.Empty;
        }

        if (normalized.Contains("://", StringComparison.Ordinal))
        {
            return null;
        }

        string[] segments = normalized.Split('/', StringSplitOptions.RemoveEmptyEntries);
        List<string> escapedSegments = new(segments.Length);
        foreach (string segment in segments)
        {
            if (ContainsInvalidPercentEncoding(segment))
            {
                return null;
            }

            string unescapedSegment;
            try
            {
                unescapedSegment = Uri.UnescapeDataString(segment);
            }
            catch (UriFormatException)
            {
                return null;
            }

            if (segment.Equals(".", StringComparison.Ordinal)
                || segment.Equals("..", StringComparison.Ordinal)
                || unescapedSegment.Equals(".", StringComparison.Ordinal)
                || unescapedSegment.Equals("..", StringComparison.Ordinal))
            {
                return null;
            }

            escapedSegments.Add(Uri.EscapeDataString(unescapedSegment));
        }

        return string.Join("/", escapedSegments);
    }

    private static bool ContainsInvalidPercentEncoding(string value)
    {
        for (int index = 0; index < value.Length; index++)
        {
            if (value[index] != '%')
            {
                continue;
            }

            if (index + 2 >= value.Length
                || !Uri.IsHexDigit(value[index + 1])
                || !Uri.IsHexDigit(value[index + 2]))
            {
                return true;
            }
        }

        return false;
    }
}
