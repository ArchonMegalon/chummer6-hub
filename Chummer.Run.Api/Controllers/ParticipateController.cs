using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.ViewModels;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;

namespace Chummer.Run.Api.Controllers;

[NonController]
public sealed class ParticipateController : Controller
{
    private readonly HubIdentityClient _identity;
    private readonly HubPageChromeService _chrome;
    private readonly IConfiguration _configuration;
    private readonly IHttpClientFactory? _httpClientFactory;
    private readonly ILogger<ParticipateController> _logger;

    public ParticipateController(
        HubIdentityClient identity,
        HubPageChromeService chrome,
        IConfiguration configuration,
        ILogger<ParticipateController> logger,
        IHttpClientFactory? httpClientFactory = null)
    {
        _identity = identity;
        _chrome = chrome;
        _configuration = configuration;
        _logger = logger;
        _httpClientFactory = httpClientFactory;
    }

    [HttpGet("/partizipate")]
    [Produces("text/html")]
    public Task<IActionResult> ParticipateAliasPage(CancellationToken cancellationToken)
    {
        _ = cancellationToken;
        string target = $"/participate{Request.QueryString}";
        return Task.FromResult<IActionResult>(Redirect(target));
    }

    [HttpGet("/participate")]
    [Produces("text/html")]
    public async Task<IActionResult> ParticipatePage(CancellationToken cancellationToken)
    {
        FirstPartyParticipateBoardViewModel model =
            await BuildFirstPartyParticipateBoardAsync(cancellationToken, "/participate").ConfigureAwait(false);

        if (!model.EmbeddedBoardEnabled)
        {
            model = model with
            {
                HostedBoardHref = null,
                EmbeddedBoardHref = null,
                DirectBoardHref = null,
                StatusLabel = "Offline",
                SyncedLabel = "Board offline right now"
            };
        }

        return View("~/Views/PublicLanding/Partizipate.cshtml", model);
    }

    [HttpGet("/partizipate/{**boardPath}")]
    public Task<IActionResult> ParticipateBoardProxyLegacyAlias(string? boardPath, CancellationToken cancellationToken)
    {
        _ = cancellationToken;
        if (string.IsNullOrWhiteSpace(boardPath))
        {
            return Task.FromResult<IActionResult>(Redirect($"/participate{Request.QueryString}"));
        }

        string normalizedBoardPath = NormalizeParticipateBoardPath(boardPath);
        string pathPrefix = string.IsNullOrWhiteSpace(normalizedBoardPath)
            ? string.Empty
            : $"/{normalizedBoardPath}";
        return Task.FromResult<IActionResult>(Redirect($"/participate{pathPrefix}{Request.QueryString}"));
    }

    [HttpGet("/participate/{**boardPath}")]
    public IActionResult ParticipateBoardProxyAlias(string? boardPath)
    {
        if (string.IsNullOrWhiteSpace(boardPath))
        {
            return Redirect($"/participate{Request.QueryString}");
        }

        string normalizedBoardPath = NormalizeParticipateBoardPath(boardPath);
        string suffix = string.IsNullOrWhiteSpace(normalizedBoardPath)
            ? string.Empty
            : $"/{normalizedBoardPath}";
        return Redirect($"/participate/board{suffix}{Request.QueryString}");
    }

    [HttpGet("/participate/board")]
    [HttpGet("/participate/board/{**boardPath}")]
    public async Task<IActionResult> ParticipateBoardProxy(string? boardPath, CancellationToken cancellationToken)
        => await ParticipateBoardProxyCore(
            NormalizeParticipateBoardPath(boardPath),
            cancellationToken).ConfigureAwait(false);

    [HttpGet("/participate/frame")]
    [HttpGet("/participate/frame/{**boardPath}")]
    public IActionResult ParticipateBoardFrame(string? boardPath)
    {
        Uri? upstream = ResolveProductLiftHostedBoardUri();
        if (upstream is null || ShouldShortCircuitHostedBoardUpstream(upstream))
        {
            return Redirect("/participate");
        }

        string normalizedBoardPath = NormalizeParticipateBoardPath(boardPath);
        Uri target = string.IsNullOrWhiteSpace(normalizedBoardPath)
            ? AppendQueryString(upstream, Request.QueryString.Value)
            : AppendQueryString(ResolveHostedBoardContentUri(upstream, normalizedBoardPath), Request.QueryString.Value);
        return Redirect(target.ToString());
    }

    [AcceptVerbs("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", Route = "/http_api/{**boardPath}")]
    public async Task<IActionResult> ParticipateBoardRootHttpApiProxy(string? boardPath, CancellationToken cancellationToken)
        => await ParticipateBoardRootResourceProxy("http_api", boardPath, cancellationToken).ConfigureAwait(false);

    [HttpGet("/translations_i18n/{**boardPath}")]
    public async Task<IActionResult> ParticipateBoardRootTranslationsProxy(string? boardPath, CancellationToken cancellationToken)
        => await ParticipateBoardRootResourceProxy("translations_i18n", boardPath, cancellationToken).ConfigureAwait(false);

    [HttpGet("/loading.svg")]
    public async Task<IActionResult> ParticipateBoardRootLoadingImageProxy(CancellationToken cancellationToken)
        => await ParticipateBoardRootResourceProxy("loading.svg", null, cancellationToken).ConfigureAwait(false);

    [HttpGet("/participate/provider-assets/{assetHost}/{**assetPath}")]
    public async Task<IActionResult> ParticipateBoardProviderAssetProxy(string assetHost, string? assetPath, CancellationToken cancellationToken)
        => await HostedBoardProviderAssetProxyCore(assetHost, assetPath, cancellationToken).ConfigureAwait(false);

    private async Task<FirstPartyParticipateBoardViewModel> BuildFirstPartyParticipateBoardAsync(
        CancellationToken cancellationToken,
        string currentPath = "/participate",
        string? boardPath = null)
    {
        AuthenticatedHubSubject? subject = await TryGetOptionalSubjectAsync(cancellationToken).ConfigureAwait(false);
        Uri? hostedBoardUpstream = ResolveProductLiftHostedBoardUri();
        bool hostedBoardAvailable = hostedBoardUpstream is not null && !ShouldShortCircuitHostedBoardUpstream(hostedBoardUpstream);
        bool boardRoute = currentPath.StartsWith("/participate/board", StringComparison.OrdinalIgnoreCase);
        string normalizedBoardPath = NormalizeParticipateBoardPath(boardPath);
        string? embeddedBoardHref = hostedBoardAvailable ? BuildParticipateFrameHref(normalizedBoardPath) : null;
        string? directBoardHref = hostedBoardAvailable ? BuildParticipateBoardRouteHref(normalizedBoardPath) : null;
        string? boardShellHref = hostedBoardAvailable && !boardRoute
            ? BuildParticipateBoardRouteHref(normalizedBoardPath)
            : null;
        string? entryHref = subject is null
            ? BuildParticipateSignInHref("/participate")
            : "/account";
        string entryLabel = subject is null ? "Sign in" : "Account";
        string entrySummary = subject is null
            ? "Browse now. Sign in later if you want your votes attached."
            : $"{(string.IsNullOrWhiteSpace(subject.DisplayName) ? "This account" : subject.DisplayName)} is already signed in here.";
        string? supporterHref = subject is null ? null : ResolveParticipateSupporterHref();

        return new FirstPartyParticipateBoardViewModel(
            Chrome: BuildParticipateShellChrome(currentPath, subject),
            Heading: "Participate",
            Summary: "Participate",
            StatusLabel: hostedBoardAvailable ? "Open" : "Offline",
            Posts: Array.Empty<FirstPartyParticipatePostViewModel>(),
            FallbackItems: Array.Empty<ParticipateItemViewModel>(),
            TotalRequestCount: 0,
            SyncedLabel: hostedBoardAvailable ? "Board is live." : "Board offline right now",
            RoadmapHref: "/roadmap",
            HostedBoardHref: boardShellHref,
            SupportHref: "/contact",
            RetryHref: BuildParticipateBoardRouteHref(normalizedBoardPath),
            SupporterHref: supporterHref,
            LoadedFromBoard: false,
            EmbeddedBoardEnabled: hostedBoardAvailable,
            EmbeddedBoardHref: embeddedBoardHref,
            DirectBoardHref: directBoardHref,
            EntryHref: entryHref,
            EntryLabel: entryLabel,
            EntrySummary: entrySummary);
    }

    private static SiteChromeViewModel BuildParticipateShellChrome(string currentPath, AuthenticatedHubSubject? subject)
        => new(
            Title: "Participate",
            Description: "Participate",
            CurrentPath: currentPath,
            PrimaryNavigation: Array.Empty<PublicNavigationLink>(),
            SecondaryNavigation: Array.Empty<PublicNavigationLink>(),
            UtilityNavigation: Array.Empty<PublicNavigationLink>(),
            HeaderActions: Array.Empty<SiteChromeActionViewModel>(),
            PublicPrimaryCta: null,
            Authenticated: subject is not null,
            SignedInLabel: subject is null
                ? null
                : string.IsNullOrWhiteSpace(subject.DisplayName)
                    ? "Signed in"
                    : subject.DisplayName,
            FooterCanonicalSource: string.Empty,
            FooterGeneratedNote: string.Empty,
            PublicSignalNavigation: Array.Empty<PublicNavigationLink>());

    private bool ShouldShortCircuitHostedBoardUpstream(Uri? upstream)
        => upstream is not null
            && HttpContext?.RequestServices.GetService<IWebHostEnvironment>()?.EnvironmentName == "Development"
            && upstream.Host.EndsWith(".example.test", StringComparison.OrdinalIgnoreCase);

    private async Task<IActionResult> ParticipateBoardFallbackAsync(CancellationToken cancellationToken, string currentPath = "/participate/board")
    {
        FirstPartyParticipateBoardViewModel model = await BuildFirstPartyParticipateBoardAsync(cancellationToken, currentPath).ConfigureAwait(false);
        model = model with
        {
            StatusLabel = "Offline",
            SyncedLabel = "Board offline right now",
            HostedBoardHref = null,
            EmbeddedBoardEnabled = false,
            EmbeddedBoardHref = null,
            DirectBoardHref = null
        };
        return View("~/Views/PublicLanding/Partizipate.cshtml", model);
    }

    private async Task<IActionResult> ParticipateBoardProxyCore(
        string? boardPath,
        CancellationToken cancellationToken,
        string localOrigin = "/participate/board",
        string localBaseHref = "/participate/board/",
        string? canonicalHref = null,
        string fallbackPath = "/participate/board")
    {
        Uri? upstream = ResolveProductLiftHostedBoardUri();
        if (upstream is null)
        {
            return await ParticipateBoardFallbackAsync(cancellationToken, fallbackPath).ConfigureAwait(false);
        }

        string relativePath = string.IsNullOrWhiteSpace(boardPath) ? string.Empty : boardPath.TrimStart('/');
        Uri target = string.IsNullOrWhiteSpace(relativePath)
            ? AppendQueryString(upstream, Request.QueryString.Value)
            : AppendQueryString(ResolveHostedBoardContentUri(upstream, relativePath), Request.QueryString.Value);

        try
        {
            using HttpClient client = _httpClientFactory?.CreateClient() ?? new HttpClient();
            using var outbound = new HttpRequestMessage(HttpMethod.Get, target);
            outbound.Headers.TryAddWithoutValidation("User-Agent", Request.Headers.UserAgent.ToString());
            outbound.Headers.TryAddWithoutValidation("Accept", Request.Headers.Accept.ToArray());
            outbound.Headers.TryAddWithoutValidation("Accept-Language", Request.Headers.AcceptLanguage.ToArray());
            outbound.Headers.Referrer = upstream;

            using HttpResponseMessage response = await client.SendAsync(outbound, HttpCompletionOption.ResponseHeadersRead, cancellationToken).ConfigureAwait(false);

            if ((int)response.StatusCode >= 300 && (int)response.StatusCode < 400 && response.Headers.Location is not null)
            {
                string redirected = RewriteHostedBoardLocation(response.Headers.Location, upstream, fallbackPath, localOrigin);
                return Redirect(redirected);
            }

            string mediaType = response.Content.Headers.ContentType?.MediaType ?? "application/octet-stream";
            if (mediaType.StartsWith("text/html", StringComparison.OrdinalIgnoreCase))
            {
                string html = await response.Content.ReadAsStringAsync(cancellationToken).ConfigureAwait(false);
                if (!response.IsSuccessStatusCode || HostedBoardHtmlLooksUnavailable(html))
                {
                    return await ParticipateBoardFallbackAsync(cancellationToken, fallbackPath).ConfigureAwait(false);
                }

                string rewritten = RewriteParticipateBoardHtml(
                    html,
                    upstream,
                    localOrigin,
                    localBaseHref,
                    canonicalHref ?? "/participate/board");
                Response.Headers["Cache-Control"] = "public, max-age=60, stale-while-revalidate=120";
                Response.Headers["Vary"] = "Accept-Encoding";
                return Content(rewritten, "text/html; charset=utf-8");
            }

            byte[] bytes = await response.Content.ReadAsByteArrayAsync(cancellationToken).ConfigureAwait(false);
            CopySafeProxyHeaders(response);
            return File(bytes, mediaType);
        }
        catch (HttpRequestException ex)
        {
            _logger.LogWarning(ex, "Participate board proxy could not reach upstream board.");
            return await ParticipateBoardFallbackAsync(cancellationToken, fallbackPath).ConfigureAwait(false);
        }
        catch (TaskCanceledException ex) when (!cancellationToken.IsCancellationRequested)
        {
            _logger.LogWarning(ex, "Participate board proxy timed out.");
            return await ParticipateBoardFallbackAsync(cancellationToken, fallbackPath).ConfigureAwait(false);
        }
    }

    private async Task<IActionResult> ParticipateBoardRootResourceProxy(string rootSegment, string? boardPath, CancellationToken cancellationToken)
    {
        Uri? upstream = ResolveProductLiftHostedBoardUri();
        if (upstream is null)
        {
            return NotFound();
        }

        string relativePath = string.IsNullOrWhiteSpace(boardPath)
            ? rootSegment
            : $"{rootSegment.TrimEnd('/')}/{boardPath.TrimStart('/')}";
        Uri upstreamOrigin = new($"{upstream.GetLeftPart(UriPartial.Authority).TrimEnd('/')}/");
        Uri target = AppendQueryString(new Uri(upstreamOrigin, relativePath), Request.QueryString.Value);

        try
        {
            using HttpClient client = _httpClientFactory?.CreateClient() ?? new HttpClient();
            using var outbound = new HttpRequestMessage(new HttpMethod(Request.Method), target);
            CopySafeBoardRequestHeaders(outbound);

            if (HttpMethods.IsPost(Request.Method)
                || HttpMethods.IsPut(Request.Method)
                || HttpMethods.IsPatch(Request.Method)
                || HttpMethods.IsDelete(Request.Method))
            {
                outbound.Content = new StreamContent(Request.Body);
                if (!string.IsNullOrWhiteSpace(Request.ContentType))
                {
                    outbound.Content.Headers.TryAddWithoutValidation("Content-Type", Request.ContentType);
                }
            }

            using HttpResponseMessage response = await client.SendAsync(outbound, HttpCompletionOption.ResponseHeadersRead, cancellationToken).ConfigureAwait(false);
            string mediaType = response.Content.Headers.ContentType?.MediaType ?? "application/octet-stream";
            byte[] bytes = await response.Content.ReadAsByteArrayAsync(cancellationToken).ConfigureAwait(false);
            CopySafeProxyHeaders(response);
            return File(bytes, mediaType);
        }
        catch (HttpRequestException ex)
        {
            _logger.LogWarning(ex, "Participate board root proxy could not reach upstream board resource {RootSegment}.", rootSegment);
            return NotFound();
        }
        catch (TaskCanceledException ex) when (!cancellationToken.IsCancellationRequested)
        {
            _logger.LogWarning(ex, "Participate board root proxy timed out for upstream board resource {RootSegment}.", rootSegment);
            return NotFound();
        }
    }

    private async Task<IActionResult> HostedBoardProviderAssetProxyCore(string assetHost, string? assetPath, CancellationToken cancellationToken)
    {
        string normalizedHost = assetHost.Trim().ToLowerInvariant();
        if (normalizedHost is not ("media" or "cdn") || string.IsNullOrWhiteSpace(assetPath))
        {
            return NotFound();
        }

        string providerDomain = string.Concat("product", "lift.dev");
        Uri target = AppendQueryString(
            new Uri($"https://{normalizedHost}.{providerDomain}/{assetPath.TrimStart('/')}"),
            Request.QueryString.Value);

        try
        {
            using HttpClient client = _httpClientFactory?.CreateClient() ?? new HttpClient();
            using var outbound = new HttpRequestMessage(HttpMethod.Get, target);
            outbound.Headers.TryAddWithoutValidation("User-Agent", Request.Headers.UserAgent.ToArray());
            outbound.Headers.TryAddWithoutValidation("Accept", Request.Headers.Accept.ToArray());
            outbound.Headers.TryAddWithoutValidation("Accept-Language", Request.Headers.AcceptLanguage.ToArray());

            using HttpResponseMessage response = await client.SendAsync(outbound, HttpCompletionOption.ResponseHeadersRead, cancellationToken).ConfigureAwait(false);
            if (!response.IsSuccessStatusCode)
            {
                return StatusCode((int)response.StatusCode);
            }

            string mediaType = response.Content.Headers.ContentType?.MediaType ?? "application/octet-stream";
            byte[] bytes = await response.Content.ReadAsByteArrayAsync(cancellationToken).ConfigureAwait(false);
            CopySafeProxyHeaders(response);
            return File(bytes, mediaType);
        }
        catch (HttpRequestException ex)
        {
            _logger.LogWarning(ex, "Participate board provider asset proxy could not reach {AssetHost}.", normalizedHost);
            return NotFound();
        }
        catch (TaskCanceledException ex) when (!cancellationToken.IsCancellationRequested)
        {
            _logger.LogWarning(ex, "Participate board provider asset proxy timed out for {AssetHost}.", normalizedHost);
            return NotFound();
        }
    }

    private string ResolvePublicHomeHref()
    {
        string configured = (_configuration["CHUMMER_PUBLIC_BASE_URL"] ?? "https://chummer.run").Trim();
        if (!Uri.TryCreate(configured, UriKind.Absolute, out Uri? uri))
        {
            return "https://chummer.run/";
        }

        return $"{uri.GetLeftPart(UriPartial.Authority).TrimEnd('/')}/";
    }

    private async Task<AuthenticatedHubSubject?> TryGetOptionalSubjectAsync(CancellationToken cancellationToken)
    {
        try
        {
            return await _identity.RequireSubjectAsync(Request, cancellationToken).ConfigureAwait(false);
        }
        catch (HubRequestAuthException ex) when (ex.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
        {
            return null;
        }
    }

    private static string NormalizeParticipateBoardPath(string? boardPath)
    {
        string relativePath = string.IsNullOrWhiteSpace(boardPath) ? string.Empty : boardPath.TrimStart('/');
        if (relativePath.StartsWith("board/", StringComparison.OrdinalIgnoreCase))
        {
            return relativePath["board/".Length..];
        }

        return string.Equals(relativePath, "board", StringComparison.OrdinalIgnoreCase)
            ? string.Empty
            : relativePath;
    }

    private static string BuildParticipateSignInHref(string targetPath = "/participate")
        => $"/login?next={Uri.EscapeDataString(string.IsNullOrWhiteSpace(targetPath) ? "/participate" : targetPath)}";

    private static string BuildParticipateBoardRouteHref(string? boardPath = null)
    {
        string normalizedBoardPath = NormalizeParticipateBoardPath(boardPath);
        return string.IsNullOrWhiteSpace(normalizedBoardPath)
            ? "/participate/board"
            : $"/participate/board/{normalizedBoardPath}";
    }

    private static string BuildParticipateFrameHref(string? boardPath = null)
    {
        string normalizedBoardPath = NormalizeParticipateBoardPath(boardPath);
        string route = string.IsNullOrWhiteSpace(normalizedBoardPath)
            ? "/participate/board"
            : $"/participate/board/{normalizedBoardPath}";
        return $"{route}?embed=1";
    }

    private static Uri ResolveHostedBoardContentUri(Uri upstream, string relativePath)
    {
        string normalizedPath = string.IsNullOrWhiteSpace(relativePath)
            ? string.Empty
            : relativePath.TrimStart('/');
        if (string.IsNullOrWhiteSpace(normalizedPath))
        {
            return upstream;
        }

        Uri directory = new($"{upstream.AbsoluteUri.TrimEnd('/')}/");
        return new Uri(directory, normalizedPath);
    }

    private static bool HostedBoardHtmlLooksUnavailable(string html)
    {
        if (string.IsNullOrWhiteSpace(html))
        {
            return true;
        }

        ReadOnlySpan<string> phrases =
        [
            "something went wrong on our side",
            "could not load posts",
            "please check your internet connection and try again",
            "network error",
            "network error while loading tab configuration",
            string.Concat("please try again or contact ", "support@", "productlift.dev")
        ];

        foreach (string phrase in phrases)
        {
            if (html.Contains(phrase, StringComparison.OrdinalIgnoreCase))
            {
                return true;
            }
        }

        return false;
    }

    private Uri? ResolveProductLiftHostedBoardUri()
        => ProductLiftHostedUriResolver.TryResolve(_configuration["CHUMMER_PRODUCTLIFT_FEEDBACK_URL"]?.Trim());

    private static Uri AppendQueryString(Uri baseUri, string? queryString)
    {
        if (string.IsNullOrWhiteSpace(queryString))
        {
            return baseUri;
        }

        string raw = queryString.StartsWith('?') ? queryString : $"?{queryString}";
        var builder = new UriBuilder(baseUri)
        {
            Query = raw.TrimStart('?')
        };
        return builder.Uri;
    }

    private static string RewriteHostedBoardLocation(Uri location, Uri upstream, string fallbackPath, string localPrefix)
    {
        Uri absolute = location.IsAbsoluteUri ? location : new Uri(upstream, location);
        if (!Uri.Compare(absolute, upstream, UriComponents.SchemeAndServer, UriFormat.Unescaped, StringComparison.OrdinalIgnoreCase).Equals(0))
        {
            return fallbackPath;
        }

        string relative = upstream.MakeRelativeUri(absolute).ToString();
        if (string.IsNullOrWhiteSpace(relative))
        {
            return fallbackPath;
        }

        return $"{localPrefix}/{relative}";
    }

    private static string NormalizeHostedBoardFirstPartyHrefs(string html, string localOrigin)
    {
        string normalizedOrigin = string.IsNullOrWhiteSpace(localOrigin)
            ? string.Empty
            : localOrigin.TrimEnd('/');
        if (string.IsNullOrEmpty(normalizedOrigin))
        {
            return html;
        }

        string[] routes =
        [
            "/",
            "/participate",
            "/participate/board",
            "/participate/frame",
            "/partizipate",
            "/roadmap",
            "/changelog",
            "/downloads",
            "/status",
            "/help",
            "/contact",
            "/faq",
            "/login",
            "/signup",
            "/what-is-chummer"
        ];

        string rewritten = html;
        foreach (string route in routes)
        {
            string prefixed = $"{normalizedOrigin}{route}";
            rewritten = rewritten.Replace($"href=\"{prefixed}\"", $"href=\"{route}\"", StringComparison.OrdinalIgnoreCase);
            rewritten = rewritten.Replace($"href='{prefixed}'", $"href='{route}'", StringComparison.OrdinalIgnoreCase);
        }

        return rewritten;
    }

    private string RewriteParticipateBoardHtml(
        string html,
        Uri upstream,
        string localOrigin,
        string localBaseHref,
        string canonicalHref)
    {
        string upstreamOrigin = upstream.GetLeftPart(UriPartial.Authority).TrimEnd('/');

        string rewritten = html.Replace(upstreamOrigin, localOrigin, StringComparison.OrdinalIgnoreCase);
        rewritten = rewritten.Replace("href=\"/", $"href=\"{localOrigin}/", StringComparison.OrdinalIgnoreCase);
        rewritten = rewritten.Replace("src=\"/", $"src=\"{localOrigin}/", StringComparison.OrdinalIgnoreCase);
        rewritten = rewritten.Replace("action=\"/", $"action=\"{localOrigin}/", StringComparison.OrdinalIgnoreCase);
        rewritten = rewritten.Replace("content=\"/", $"content=\"{localOrigin}/", StringComparison.OrdinalIgnoreCase);
        rewritten = NormalizeHostedBoardFirstPartyHrefs(rewritten, localOrigin);

        if (!rewritten.Contains("<base ", StringComparison.OrdinalIgnoreCase))
        {
            rewritten = Regex.Replace(
                rewritten,
                "<head(.*?)>",
                $"<head$1><base href=\"{localBaseHref}\" />",
                RegexOptions.IgnoreCase | RegexOptions.Singleline,
                TimeSpan.FromMilliseconds(250));
        }

        rewritten = Regex.Replace(
            rewritten,
            @"<link\b(?=[^>]*\brel\s*=\s*[""']canonical[""'])[^>]*>",
            string.Empty,
            RegexOptions.IgnoreCase | RegexOptions.Singleline,
            TimeSpan.FromMilliseconds(250));
        rewritten = Regex.Replace(
            rewritten,
            @"(<base\b[^>]*>)",
            $"$1<link rel=\"canonical\" href=\"{canonicalHref}\" />",
            RegexOptions.IgnoreCase | RegexOptions.Singleline,
            TimeSpan.FromMilliseconds(250));
        rewritten = InjectParticipateBoardFrameStyles(rewritten);
        rewritten = Regex.Replace(
            rewritten,
            @"(<meta\b[^>]*\b(?:property|name)\s*=\s*[""'](?:og:url|twitter:url)[""'][^>]*\bcontent\s*=\s*[""'])[^""']*([""'][^>]*>)",
            $"$1{canonicalHref}$2",
            RegexOptions.IgnoreCase | RegexOptions.Singleline,
            TimeSpan.FromMilliseconds(250));

        rewritten = Regex.Replace(
            rewritten,
            "<!--.*?ProductLift.*?-->",
            string.Empty,
            RegexOptions.IgnoreCase | RegexOptions.Singleline,
            TimeSpan.FromMilliseconds(250));
        rewritten = Regex.Replace(
            rewritten,
            "<meta[^>]+name=\"generator\"[^>]*>",
            string.Empty,
            RegexOptions.IgnoreCase,
            TimeSpan.FromMilliseconds(250));
        rewritten = RemoveHostedBoardAuthLinks(rewritten);
        rewritten = RewriteHostedBoardAssetHosts(rewritten, "/participate/provider-assets");
        rewritten = rewritten.Replace("Powered by ProductLift", "Hosted by Chummer", StringComparison.OrdinalIgnoreCase);
        rewritten = Regex.Replace(
            rewritten,
            @">(\s*)ProductLift(\s*)<",
            ">$1Chummer$2<",
            RegexOptions.IgnoreCase,
            TimeSpan.FromMilliseconds(250));
        rewritten = Regex.Replace(
            rewritten,
            @"\b(aria-label|title)\s*=\s*(""|')ProductLift\2",
            "$1=$2Chummer$2",
            RegexOptions.IgnoreCase,
            TimeSpan.FromMilliseconds(250));

        if (!rewritten.Contains("data-chummer-home-link-patch", StringComparison.Ordinal))
        {
            string publicHomeHref = ResolvePublicHomeHref();
            string homeLinkPatch = """
<script data-chummer-home-link-patch>
document.addEventListener('DOMContentLoaded', function () {
  const candidates = Array.from(document.querySelectorAll('header a[href], nav a[href], [class*="header"] a[href], [class*="brand"] a[href], [class*="logo"] a[href]'));
  const brand = candidates.find(function (anchor) {
    if (!(anchor instanceof HTMLAnchorElement)) {
      return false;
    }

    const href = (anchor.getAttribute('href') || '').trim();
    if (!href) {
      return false;
    }

    const text = (anchor.textContent || '').trim().toLowerCase();
    const hasBrandText = text === 'chummer' || text === ('product' + 'lift') || text.includes('feedback') || text.includes('roadmap');
    const hasLogo = !!anchor.querySelector('img, svg');
    return hasBrandText || hasLogo;
  });

  if (!brand) {
    return;
  }

  brand.setAttribute('href', '__CHUMMER_PUBLIC_HOME_HREF__');
  brand.setAttribute('target', '_top');
  brand.setAttribute('rel', 'noopener');
});
</script>
"""
                .Replace("__CHUMMER_PUBLIC_HOME_HREF__", publicHomeHref, StringComparison.Ordinal);

            rewritten = rewritten.Contains("</head>", StringComparison.OrdinalIgnoreCase)
                ? Regex.Replace(rewritten, "</head>", $"{homeLinkPatch}</head>", RegexOptions.IgnoreCase, TimeSpan.FromMilliseconds(250))
                : homeLinkPatch + rewritten;
        }

        return rewritten;
    }

    private static string RemoveHostedBoardAuthLinks(string html)
    {
        if (string.IsNullOrWhiteSpace(html))
        {
            return string.Empty;
        }

        return Regex.Replace(
            html,
            @"<a\b(?=[^>]*\bhref\s*=\s*(?:""[^""]*(?:login|signin|sign-in|signup|sign-up|register)[^""]*""|'[^']*(?:login|signin|sign-in|signup|sign-up|register)[^']*'|[^\s>]*(?:login|signin|sign-in|signup|sign-up|register)[^\s>]*))[^>]*>.*?</a>",
            string.Empty,
            RegexOptions.IgnoreCase | RegexOptions.Singleline,
            TimeSpan.FromMilliseconds(250));
    }

    private static string RewriteHostedBoardAssetHosts(string html, string assetProxyBasePath)
    {
        string providerDomain = string.Concat("product", "lift.dev");
        string rewritten = Regex.Replace(
            html,
            $"https://(?<assetHost>media|cdn)\\.{Regex.Escape(providerDomain)}(?=[/\"'>\\s])",
            match => $"{assetProxyBasePath}/{match.Groups["assetHost"].Value}",
            RegexOptions.IgnoreCase,
            TimeSpan.FromMilliseconds(250));
        return Regex.Replace(
            rewritten,
            @"https://(?<assetHost>media|cdn)\.chummer(?=[/""'>\s])",
            match => $"{assetProxyBasePath}/{match.Groups["assetHost"].Value}",
            RegexOptions.IgnoreCase,
            TimeSpan.FromMilliseconds(250));
    }

    private static string InjectParticipateBoardFrameStyles(string html)
    {
        if (string.IsNullOrWhiteSpace(html)
            || html.Contains("data-chummer-board-frame-style", StringComparison.Ordinal))
        {
            return html;
        }

        const string style = """
<style data-chummer-board-frame-style>
  #menubar,
  #global_search_mount {
    display: none !important;
  }

  body {
    background: #101311 !important;
  }

  #page-content-wrapper,
  #main_container,
  #main_container.container,
  .container:not(.auth-container) {
    max-width: 100% !important;
  }

  #main_container,
  #main_container.container {
    padding-top: 0 !important;
  }

  .container:not(.auth-container) {
    padding-inline: 0 !important;
  }
</style>
""";

        return rewrittenHeadInsert(html, style);

        static string rewrittenHeadInsert(string source, string markup)
            => source.Contains("</head>", StringComparison.OrdinalIgnoreCase)
                ? Regex.Replace(source, "</head>", $"{markup}</head>", RegexOptions.IgnoreCase, TimeSpan.FromMilliseconds(250))
                : markup + source;
    }

    private string? ResolveParticipateSupporterHref()
    {
        BrilliantDirectoriesBillingService? billing = HttpContext?.RequestServices.GetService<BrilliantDirectoriesBillingService>();
        try
        {
            if (billing is null)
            {
                return "/account/billing";
            }

            _ = billing.GetPage();
            return "/account/billing";
        }
        catch (InvalidOperationException)
        {
            return null;
        }
    }

    private void CopySafeBoardRequestHeaders(HttpRequestMessage outbound)
    {
        outbound.Headers.TryAddWithoutValidation("User-Agent", Request.Headers.UserAgent.ToArray());
        outbound.Headers.TryAddWithoutValidation("Accept", Request.Headers.Accept.ToArray());
        outbound.Headers.TryAddWithoutValidation("Accept-Language", Request.Headers.AcceptLanguage.ToArray());
        outbound.Headers.TryAddWithoutValidation("X-Requested-With", Request.Headers["X-Requested-With"].ToArray());
        outbound.Headers.TryAddWithoutValidation("X-CSRF-TOKEN", Request.Headers["X-CSRF-TOKEN"].ToArray());
        outbound.Headers.TryAddWithoutValidation("X-XSRF-TOKEN", Request.Headers["X-XSRF-TOKEN"].ToArray());
    }

    private void CopySafeProxyHeaders(HttpResponseMessage response)
    {
        foreach (var header in response.Headers)
        {
            if (string.Equals(header.Key, "transfer-encoding", StringComparison.OrdinalIgnoreCase)
                || string.Equals(header.Key, "location", StringComparison.OrdinalIgnoreCase)
                || string.Equals(header.Key, "set-cookie", StringComparison.OrdinalIgnoreCase)
                || string.Equals(header.Key, "connection", StringComparison.OrdinalIgnoreCase)
                || string.Equals(header.Key, "keep-alive", StringComparison.OrdinalIgnoreCase)
                || string.Equals(header.Key, "proxy-authenticate", StringComparison.OrdinalIgnoreCase)
                || string.Equals(header.Key, "proxy-authorization", StringComparison.OrdinalIgnoreCase)
                || string.Equals(header.Key, "te", StringComparison.OrdinalIgnoreCase)
                || string.Equals(header.Key, "trailer", StringComparison.OrdinalIgnoreCase)
                || string.Equals(header.Key, "upgrade", StringComparison.OrdinalIgnoreCase)
                || string.Equals(header.Key, "content-security-policy", StringComparison.OrdinalIgnoreCase)
                || string.Equals(header.Key, "x-frame-options", StringComparison.OrdinalIgnoreCase))
            {
                continue;
            }

            Response.Headers[header.Key] = header.Value.ToArray();
        }

        foreach (var header in response.Content.Headers)
        {
            if (string.Equals(header.Key, "content-security-policy", StringComparison.OrdinalIgnoreCase)
                || string.Equals(header.Key, "set-cookie", StringComparison.OrdinalIgnoreCase)
                || string.Equals(header.Key, "x-frame-options", StringComparison.OrdinalIgnoreCase))
            {
                continue;
            }

            Response.Headers[header.Key] = header.Value.ToArray();
        }

        Response.Headers.Remove("transfer-encoding");
    }
}
