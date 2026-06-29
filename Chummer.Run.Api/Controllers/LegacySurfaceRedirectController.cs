using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Configuration;
using Microsoft.Net.Http.Headers;
using System.Net.WebSockets;

namespace Chummer.Run.Api.Controllers;

[ApiController]
public sealed class LegacySurfaceRedirectController : ControllerBase
{
    private static readonly HashSet<string> HopByHopRequestHeaders = new(StringComparer.OrdinalIgnoreCase)
    {
        HeaderNames.Connection,
        HeaderNames.Host,
        HeaderNames.KeepAlive,
        HeaderNames.ProxyAuthenticate,
        HeaderNames.ProxyAuthorization,
        HeaderNames.TE,
        HeaderNames.Trailer,
        HeaderNames.TransferEncoding,
        HeaderNames.Upgrade
    };

    private static readonly HashSet<string> HopByHopResponseHeaders = new(StringComparer.OrdinalIgnoreCase)
    {
        HeaderNames.Connection,
        HeaderNames.KeepAlive,
        HeaderNames.ProxyAuthenticate,
        HeaderNames.ProxyAuthorization,
        HeaderNames.TE,
        HeaderNames.Trailer,
        HeaderNames.TransferEncoding,
        HeaderNames.Upgrade
    };

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

    [AcceptVerbs("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS")]
    [Route("/blazor")]
    [Route("/blazor/{**path}")]
    public async Task<IActionResult> Workbench(string? path, CancellationToken cancellationToken)
        => await ProxyBrowserSurfaceAsync(_blazorUpstream, "/blazor", path, cancellationToken).ConfigureAwait(false);

    [AcceptVerbs("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS")]
    [Route("/app")]
    [Route("/app/{**path}")]
    public async Task<IActionResult> App(string? path, CancellationToken cancellationToken)
    {
        Uri? appUpstream = _blazorUpstream is null ? null : new Uri(_blazorUpstream, "app/");
        return await ProxyBrowserSurfaceAsync(appUpstream, "/app", path, cancellationToken).ConfigureAwait(false);
    }

    [AcceptVerbs("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS")]
    [Route("/avalonia")]
    [Route("/avalonia/{**path}")]
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

        if (HttpContext.WebSockets.IsWebSocketRequest)
        {
            bool proxied = await TryProxyWebSocketAsync(target, cancellationToken).ConfigureAwait(false);
            if (!proxied)
            {
                Response.StatusCode = StatusCodes.Status503ServiceUnavailable;
            }

            return new EmptyResult();
        }

        using HttpClient client = CreateBrowserSurfaceClient();
        using var outbound = new HttpRequestMessage(new HttpMethod(Request.Method), target);
        if (RequestHasBody())
        {
            outbound.Content = new StreamContent(Request.Body);
        }

        CopyRequestHeaders(outbound);

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
            if (HopByHopResponseHeaders.Contains(header.Key))
            {
                continue;
            }

            Response.Headers[header.Key] = header.Value.ToArray();
        }

        foreach (var header in response.Content.Headers)
        {
            if (HopByHopResponseHeaders.Contains(header.Key))
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

    private HttpClient CreateBrowserSurfaceClient()
    {
        if (_httpClientFactory is not null)
        {
            return _httpClientFactory.CreateClient();
        }

        return new HttpClient(new HttpClientHandler
        {
            AllowAutoRedirect = false,
            UseCookies = false
        });
    }

    private bool RequestHasBody()
        => Request.ContentLength.GetValueOrDefault() > 0
           || Request.Headers.ContainsKey(HeaderNames.TransferEncoding);

    private void CopyRequestHeaders(HttpRequestMessage outbound)
    {
        foreach (var header in Request.Headers)
        {
            if (HopByHopRequestHeaders.Contains(header.Key))
            {
                continue;
            }

            if (!outbound.Headers.TryAddWithoutValidation(header.Key, header.Value.ToArray()))
            {
                outbound.Content?.Headers.TryAddWithoutValidation(header.Key, header.Value.ToArray());
            }
        }

        outbound.Headers.Referrer = outbound.RequestUri is null
            ? null
            : new Uri($"{outbound.RequestUri.Scheme}://{outbound.RequestUri.Authority}/");
    }

    private async Task<bool> TryProxyWebSocketAsync(Uri target, CancellationToken cancellationToken)
    {
        Uri webSocketTarget = ConvertToWebSocketUri(target);
        using var upstreamSocket = new ClientWebSocket();
        upstreamSocket.Options.KeepAliveInterval = TimeSpan.FromSeconds(30);
        CopyWebSocketRequestHeaders(upstreamSocket.Options);

        try
        {
            await upstreamSocket.ConnectAsync(webSocketTarget, cancellationToken).ConfigureAwait(false);
        }
        catch (WebSocketException)
        {
            return false;
        }
        catch (HttpRequestException)
        {
            return false;
        }
        catch (TaskCanceledException) when (!cancellationToken.IsCancellationRequested)
        {
            return false;
        }

        using WebSocket downstreamSocket = await HttpContext.WebSockets.AcceptWebSocketAsync(
            string.IsNullOrWhiteSpace(upstreamSocket.SubProtocol) ? null : upstreamSocket.SubProtocol).ConfigureAwait(false);

        Task upstreamPump = RelayWebSocketAsync(downstreamSocket, upstreamSocket, cancellationToken);
        Task downstreamPump = RelayWebSocketAsync(upstreamSocket, downstreamSocket, cancellationToken);
        await Task.WhenAll(upstreamPump, downstreamPump).ConfigureAwait(false);
        return true;
    }

    private void CopyWebSocketRequestHeaders(ClientWebSocketOptions options)
    {
        foreach (var header in Request.Headers)
        {
            if (HopByHopRequestHeaders.Contains(header.Key)
                || header.Key.StartsWith("Sec-WebSocket-", StringComparison.OrdinalIgnoreCase))
            {
                continue;
            }

            options.SetRequestHeader(header.Key, header.Value.ToString());
        }

        if (Request.Headers.TryGetValue(HeaderNames.SecWebSocketProtocol, out var protocolValues))
        {
            IEnumerable<string> requestProtocols = protocolValues
                .Where(static value => !string.IsNullOrWhiteSpace(value))
                .Select(static value => value!);
            foreach (string protocol in requestProtocols
                         .SelectMany(static value => value.Split(',', StringSplitOptions.TrimEntries | StringSplitOptions.RemoveEmptyEntries))
                         .Distinct(StringComparer.Ordinal))
            {
                options.AddSubProtocol(protocol);
            }
        }
    }

    private static async Task RelayWebSocketAsync(WebSocket source, WebSocket destination, CancellationToken cancellationToken)
    {
        byte[] buffer = new byte[16 * 1024];

        try
        {
            while (!cancellationToken.IsCancellationRequested
                   && source.State is WebSocketState.Open or WebSocketState.CloseReceived
                   && destination.State is WebSocketState.Open or WebSocketState.CloseReceived)
            {
                WebSocketReceiveResult result = await source.ReceiveAsync(buffer, cancellationToken).ConfigureAwait(false);
                if (result.MessageType == WebSocketMessageType.Close)
                {
                    if (destination.State == WebSocketState.Open || destination.State == WebSocketState.CloseReceived)
                    {
                        await destination.CloseOutputAsync(
                            result.CloseStatus ?? WebSocketCloseStatus.NormalClosure,
                            result.CloseStatusDescription,
                            CancellationToken.None).ConfigureAwait(false);
                    }

                    return;
                }

                await destination.SendAsync(
                    buffer.AsMemory(0, result.Count),
                    result.MessageType,
                    result.EndOfMessage,
                    cancellationToken).ConfigureAwait(false);
            }
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
        }
        catch (WebSocketException)
        {
            if (destination.State == WebSocketState.Open || destination.State == WebSocketState.CloseReceived)
            {
                await destination.CloseOutputAsync(
                    WebSocketCloseStatus.InternalServerError,
                    "browser surface proxy websocket relay failed",
                    CancellationToken.None).ConfigureAwait(false);
            }
        }
    }

    private static Uri ConvertToWebSocketUri(Uri uri)
    {
        var builder = new UriBuilder(uri);
        builder.Scheme = uri.Scheme.Equals(Uri.UriSchemeHttps, StringComparison.OrdinalIgnoreCase) ? "wss" : "ws";
        return builder.Uri;
    }
}
