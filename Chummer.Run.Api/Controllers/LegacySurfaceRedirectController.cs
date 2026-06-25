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

        HttpResponseMessage response;
        try
        {
            response = await client.SendAsync(
                outbound,
                HttpCompletionOption.ResponseHeadersRead,
                cancellationToken).ConfigureAwait(false);
        }
        catch (HttpRequestException)
        {
            return BrowserSurfaceUnavailable(localBasePath);
        }
        catch (TaskCanceledException) when (!cancellationToken.IsCancellationRequested)
        {
            return BrowserSurfaceUnavailable(localBasePath);
        }

        using (response)
        {
            if ((int)response.StatusCode >= 300 && (int)response.StatusCode < 400 && response.Headers.Location is not null)
            {
                return Redirect(RewriteUpstreamLocation(response.Headers.Location, upstream, localBasePath));
            }

            if ((int)response.StatusCode >= 500)
            {
                return BrowserSurfaceUnavailable(localBasePath);
            }

            Response.StatusCode = (int)response.StatusCode;
            CopyHeaders(response);
            await using Stream stream = await response.Content.ReadAsStreamAsync(cancellationToken).ConfigureAwait(false);
            await stream.CopyToAsync(Response.Body, cancellationToken).ConfigureAwait(false);
            return new EmptyResult();
        }
    }

    private ContentResult BrowserSurfaceUnavailable(string localBasePath)
    {
        string surfaceName = string.Equals(localBasePath, "/blazor", StringComparison.OrdinalIgnoreCase)
            ? "Browser preview"
            : "Desktop preview";
        string html = $$"""
            <!doctype html>
            <html lang="en">
            <head>
                <meta charset="utf-8">
                <meta name="viewport" content="width=device-width, initial-scale=1">
                <meta name="robots" content="noindex,nofollow">
                <title>{{surfaceName}} - Chummer</title>
                <style>
                    :root { color-scheme: dark; background: #11110f; color: #f1eee7; font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
                    body { margin: 0; min-height: 100vh; display: grid; place-items: center; padding: 24px; background: #11110f; }
                    main { width: min(520px, 100%); }
                    a { color: inherit; text-decoration-thickness: 1px; text-underline-offset: 4px; }
                    h1 { margin: 0 0 12px; font-size: clamp(1.7rem, 5vw, 2.5rem); line-height: 1.02; letter-spacing: 0; }
                    p { margin: 0 0 22px; color: #c9c0b3; line-height: 1.55; }
                    .actions { display: flex; flex-wrap: wrap; gap: 12px; }
                    .button { border: 1px solid #f1eee7; border-radius: 6px; padding: 10px 14px; text-decoration: none; font-weight: 700; }
                    .muted { border-color: #4b473f; color: #c9c0b3; }
                </style>
            </head>
            <body>
                <main>
                    <h1>{{surfaceName}} is not ready right now.</h1>
                    <p>The downloadable Chummer client is the current stable path. The browser surface will come back when its service is healthy.</p>
                    <div class="actions">
                        <a class="button" href="/downloads">Download Chummer</a>
                        <a class="button muted" href="/status">Status</a>
                    </div>
                </main>
            </body>
            </html>
            """;

        return Content(html, "text/html");
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
