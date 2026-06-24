using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Configuration;

namespace Chummer.Run.Api.Controllers;

[ApiController]
public sealed class LegacySurfaceRedirectController : ControllerBase
{
    private readonly IHttpClientFactory? _httpClientFactory;
    private readonly Uri? _blazorUpstream;
    private readonly Uri? _avaloniaUpstream;

    public LegacySurfaceRedirectController(IHttpClientFactory? httpClientFactory = null, IConfiguration? configuration = null)
    {
        _httpClientFactory = httpClientFactory;
        _blazorUpstream = ResolveAbsoluteUri(
            configuration?["CHUMMER_PUBLIC_BLAZOR_PROXY_URL"]
            ?? Environment.GetEnvironmentVariable("CHUMMER_PUBLIC_BLAZOR_PROXY_URL"));
        _avaloniaUpstream = ResolveAbsoluteUri(
            configuration?["CHUMMER_PUBLIC_AVALONIA_PROXY_URL"]
            ?? Environment.GetEnvironmentVariable("CHUMMER_PUBLIC_AVALONIA_PROXY_URL"));
    }

    [HttpGet("/hub")]
    [HttpGet("/hub/{**path}")]
    public IActionResult Hub()
        => Redirect("/account");

    [HttpGet("/blazor")]
    [HttpGet("/blazor/{**path}")]
    public async Task<IActionResult> Workbench(string? path, CancellationToken cancellationToken)
        => await ProxyBrowserSurfaceAsync(_blazorUpstream, "/blazor", path, cancellationToken).ConfigureAwait(false);

    [HttpGet("/avalonia")]
    [HttpGet("/avalonia/{**path}")]
    public async Task<IActionResult> Avalonia(string? path, CancellationToken cancellationToken)
        => await ProxyBrowserSurfaceAsync(_avaloniaUpstream, "/avalonia", path, cancellationToken).ConfigureAwait(false);

    [HttpGet("/session")]
    [HttpGet("/session/{**path}")]
    public IActionResult Session()
        => Redirect("/play");

    [HttpGet("/support")]
    [HttpGet("/support/{**path}")]
    public IActionResult Support()
        => Redirect("/contact");

    [HttpGet("/coach")]
    [HttpGet("/coach/{**path}")]
    public IActionResult Coach()
        => Redirect("/status");

    private async Task<IActionResult> ProxyBrowserSurfaceAsync(
        Uri? upstream,
        string localBasePath,
        string? path,
        CancellationToken cancellationToken)
    {
        if (upstream is null)
        {
            return Redirect("/downloads");
        }

        string relativePath = string.IsNullOrWhiteSpace(path) ? string.Empty : path.TrimStart('/');
        Uri target = string.IsNullOrWhiteSpace(relativePath)
            ? AppendQueryString(upstream, Request.QueryString.Value)
            : AppendQueryString(new Uri(upstream, relativePath), Request.QueryString.Value);

        using HttpClient client = _httpClientFactory?.CreateClient() ?? new HttpClient();
        using var outbound = new HttpRequestMessage(HttpMethod.Get, target);
        outbound.Headers.TryAddWithoutValidation("User-Agent", Request.Headers.UserAgent.ToString());
        outbound.Headers.TryAddWithoutValidation("Accept", Request.Headers.Accept.ToArray());
        outbound.Headers.TryAddWithoutValidation("Accept-Language", Request.Headers.AcceptLanguage.ToArray());
        if (Request.Headers.TryGetValue("Accept-Encoding", out var acceptEncoding))
        {
            outbound.Headers.TryAddWithoutValidation("Accept-Encoding", acceptEncoding.ToArray());
        }
        outbound.Headers.Referrer = upstream;

        using HttpResponseMessage response = await client.SendAsync(
            outbound,
            HttpCompletionOption.ResponseHeadersRead,
            cancellationToken).ConfigureAwait(false);

        if ((int)response.StatusCode >= 300 && (int)response.StatusCode < 400 && response.Headers.Location is not null)
        {
            return Redirect(RewriteUpstreamLocation(response.Headers.Location, upstream, localBasePath));
        }

        Response.StatusCode = (int)response.StatusCode;
        CopyHeaders(response);
        await using Stream stream = await response.Content.ReadAsStreamAsync(cancellationToken).ConfigureAwait(false);
        await stream.CopyToAsync(Response.Body, cancellationToken).ConfigureAwait(false);
        return new EmptyResult();
    }

    private void CopyHeaders(HttpResponseMessage response)
    {
        foreach (var header in response.Headers)
        {
            if (string.Equals(header.Key, "Transfer-Encoding", StringComparison.OrdinalIgnoreCase))
            {
                continue;
            }

            Response.Headers[header.Key] = header.Value.ToArray();
        }

        foreach (var header in response.Content.Headers)
        {
            if (string.Equals(header.Key, "Transfer-Encoding", StringComparison.OrdinalIgnoreCase))
            {
                continue;
            }

            Response.Headers[header.Key] = header.Value.ToArray();
        }
    }

    private static string RewriteUpstreamLocation(Uri location, Uri upstream, string localBasePath)
    {
        if (location.IsAbsoluteUri)
        {
            if (!Uri.Compare(location, upstream, UriComponents.SchemeAndServer, UriFormat.Unescaped, StringComparison.OrdinalIgnoreCase).Equals(0))
            {
                return location.ToString();
            }

            return NormalizeLocalProxyPath(localBasePath, location.PathAndQuery);
        }

        return NormalizeLocalProxyPath(localBasePath, location.OriginalString);
    }

    private static string NormalizeLocalProxyPath(string localBasePath, string pathAndQuery)
    {
        string candidate = string.IsNullOrWhiteSpace(pathAndQuery) ? string.Empty : pathAndQuery.Trim();
        if (string.IsNullOrEmpty(candidate) || candidate == "/")
        {
            return localBasePath;
        }

        if (!candidate.StartsWith("/", StringComparison.Ordinal))
        {
            candidate = "/" + candidate;
        }

        if (candidate.StartsWith(localBasePath + "/", StringComparison.OrdinalIgnoreCase)
            || string.Equals(candidate, localBasePath, StringComparison.OrdinalIgnoreCase))
        {
            return candidate;
        }

        return localBasePath.TrimEnd('/') + candidate;
    }

    private static Uri AppendQueryString(Uri baseUri, string? queryString)
    {
        string query = string.IsNullOrWhiteSpace(queryString) ? string.Empty : queryString.Trim();
        if (string.IsNullOrEmpty(query))
        {
            return baseUri;
        }

        var builder = new UriBuilder(baseUri);
        builder.Query = query.StartsWith("?", StringComparison.Ordinal) ? query[1..] : query;
        return builder.Uri;
    }

    private static Uri? ResolveAbsoluteUri(string? raw)
    {
        string text = string.IsNullOrWhiteSpace(raw) ? string.Empty : raw.Trim();
        return Uri.TryCreate(text, UriKind.Absolute, out Uri? uri) ? uri : null;
    }
}
