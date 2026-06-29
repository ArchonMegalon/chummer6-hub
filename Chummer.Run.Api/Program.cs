using System.IO;
using System.Text.Json;
using System.Net;
using Chummer.Contracts.Presentation;
using Chummer.Run.Api;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.AspNetCore.HttpOverrides;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.StaticFiles;

var builder = WebApplication.CreateBuilder(new WebApplicationOptions
{
    Args = args,
    ContentRootPath = ResolveHubContentRoot()
});
builder.AddHubApiRuntimeGuardrails();
builder.AddHubRequestObservability();
var enableHttpsRedirection = builder.Configuration.GetValue("CHUMMER_ENABLE_HTTPS_REDIRECTION", true);
var hasHttpsListenerConfiguration = HasHttpsListenerConfiguration(builder.Configuration);

// Add services to the container.

builder.Services.AddProblemDetails();
builder.Services
    .AddControllersWithViews()
    .ConfigureApiBehaviorOptions(options =>
    {
        options.InvalidModelStateResponseFactory = context =>
        {
            var problem = new ValidationProblemDetails(context.ModelState)
            {
                Title = "Request validation failed.",
                Type = "https://chummer.run/problems/validation",
                Status = StatusCodes.Status400BadRequest
            };

            return new BadRequestObjectResult(problem);
        };
    });
var dataProtectionPath = HubRuntimePathDefaults.ResolveDataProtectionKeysPath(builder.Configuration, builder.Environment);

builder.Services.AddDataProtection()
    .SetApplicationName("Chummer.Run.Api")
    .PersistKeysToFileSystem(new DirectoryInfo(Path.GetFullPath(dataProtectionPath)));
builder.Services
    .AddHubPublicGuideContext()
    .AddHubAccountsAndCommunityContext()
    .AddHubCampaignSpineContext()
    .AddHubControlAndSupportContext()
    .AddHubInstallAndOrchestrationAdapters();
builder.Services.AddSingleton<DesktopAnalyticsBridgeService>();
builder.Services.AddHttpClient("RybbitProxy", client =>
{
    client.Timeout = TimeSpan.FromSeconds(15);
});
var trustedProxies = GetCsvValues(builder.Configuration["CHUMMER_FORWARDED_HEADER_TRUSTED_PROXIES"]);
var trustedIpNetworks = GetCsvValues(builder.Configuration["CHUMMER_FORWARDED_HEADER_TRUSTED_IP_NETWORKS"]);

builder.Services.Configure<ForwardedHeadersOptions>(options =>
{
    options.ForwardedHeaders = ForwardedHeaders.XForwardedFor | ForwardedHeaders.XForwardedProto;
    if (trustedProxies.Length == 0 && trustedIpNetworks.Length == 0)
    {
        return;
    }

    options.KnownIPNetworks.Clear();
    options.KnownProxies.Clear();

    foreach (var trustedProxy in trustedProxies)
    {
        if (IPAddress.TryParse(trustedProxy, out var parsedProxy))
        {
            options.KnownProxies.Add(parsedProxy);
        }
    }

    foreach (var trustedIpNetwork in trustedIpNetworks)
    {
        try
        {
            options.KnownIPNetworks.Add(System.Net.IPNetwork.Parse(trustedIpNetwork));
        }
        catch (FormatException)
        {
            // Ignore invalid configured trusted networks.
        }
    }
});

var app = builder.Build();
if (!HubRuntimePathDefaults.IsExplicitlyConfigured(builder.Configuration))
{
    if (HubRuntimePathDefaults.UsesTempFallback(dataProtectionPath))
    {
        app.Logger.LogWarning(
            "CHUMMER_DATA_PROTECTION_KEYS_PATH is not configured; Hub is using a temporary data-protection key ring at {Path}. OAuth and sign-in callback state can break after container churn.",
            dataProtectionPath);
    }
    else
    {
        app.Logger.LogInformation(
            "CHUMMER_DATA_PROTECTION_KEYS_PATH is not configured; Hub resolved a writable default data-protection key ring at {Path}.",
            dataProtectionPath);
    }
}

var hubGoogleAuth = app.Services.GetRequiredService<HubGoogleAuthService>();
hubGoogleAuth.ValidateProductionReadiness();
if (!hubGoogleAuth.IsConfigured())
{
    app.Logger.LogWarning("Google OIDC is not configured; Hub will start with Google sign-in surfaces disabled.");
}
const string NoIndexRobotsPolicy = "noindex, nofollow, noarchive, nosnippet, noimageindex";
const string PublicIndexRobotsPolicy = "index, follow, max-image-preview:large, max-snippet:-1, max-video-preview:-1";

// Configure the HTTP request pipeline.

app.UseExceptionHandler(errorApp =>
{
    errorApp.Run(async context =>
    {
        context.Response.StatusCode = StatusCodes.Status500InternalServerError;
        context.Response.ContentType = "application/problem+json; charset=utf-8";

        ProblemDetails problem = new()
        {
            Title = "Unexpected server error.",
            Type = "https://chummer.run/problems/server-error",
            Status = StatusCodes.Status500InternalServerError,
            Detail = "The request could not be completed. Retry, and contact support if the problem continues."
        };
        problem.Extensions["traceId"] = context.TraceIdentifier;

        await JsonSerializer.SerializeAsync(context.Response.Body, problem);
    });
});
app.UseForwardedHeaders();
if (enableHttpsRedirection && hasHttpsListenerConfiguration)
{
    app.UseHttpsRedirection();
}
else if (enableHttpsRedirection)
{
    app.Logger.LogWarning("CHUMMER_ENABLE_HTTPS_REDIRECTION is enabled, but Hub has no HTTPS listener configured. Skipping HTTPS redirection.");
}
app.Use(async (context, next) =>
{
    bool requiresNoStore = RequiresNoStoreHeaders(context.Request.Path);
    string robotsPolicy = ResolveRobotsPolicy(context.Request.Path);
    context.Response.OnStarting(() =>
    {
        context.Response.Headers["X-Robots-Tag"] = robotsPolicy;
        if (requiresNoStore)
        {
            context.Response.Headers["Cache-Control"] = "private, no-store, max-age=0";
            context.Response.Headers["CDN-Cache-Control"] = "no-store, max-age=0";
            context.Response.Headers["Cloudflare-CDN-Cache-Control"] = "no-store, max-age=0";
            context.Response.Headers["Surrogate-Control"] = "no-store";
            context.Response.Headers["Pragma"] = "no-cache";
            context.Response.Headers["Expires"] = "0";
        }

        return Task.CompletedTask;
    });

    await next();
});
app.Use(async (context, next) =>
{
    if (IsLegacyMacReleaseBootstrapArtifactPath(context.Request.Path))
    {
        context.Response.Redirect("/downloads/release-upload/bootstrap.sh", permanent: false);
        return;
    }

    await next();
});
FileExtensionContentTypeProvider contentTypeProvider = new();
contentTypeProvider.Mappings[".vtt"] = "text/vtt";
HorizonArtifactAccessTokenService horizonArtifactAccessTokens = app.Services.GetRequiredService<HorizonArtifactAccessTokenService>();

app.Use(async (context, next) =>
{
    if (horizonArtifactAccessTokens.RequiresToken(context.Request.Path)
        && !horizonArtifactAccessTokens.IsAuthorized(context.Request.Path, context.Request.Query["artifactAccess"]))
    {
        context.Response.StatusCode = StatusCodes.Status404NotFound;
        return;
    }

    await next();
});

app.UseStaticFiles(new StaticFileOptions
{
    ContentTypeProvider = contentTypeProvider,
    OnPrepareResponse = fileContext =>
    {
        fileContext.Context.Response.Headers["X-Robots-Tag"] = ResolveRobotsPolicy(fileContext.Context.Request.Path);
    }
});

app.UseWebSockets();
app.UseHubRequestObservability();
app.UseHubApiRuntimeGuardrails();
app.UseAuthorization();

app.MapGet("/api/health", () => Results.Json(new
{
    ok = true,
    service = "chummer.run.api",
    status = "pass",
    generatedAt = DateTimeOffset.UtcNow
}));
app.MapMethods("/api/rybbit/{**proxyPath}", new[] { "GET", "POST", "OPTIONS" }, ProxyRybbitAsync);
app.MapPost("/api/desktop-analytics/track", async (
    DesktopAnalyticsTrackRequest request,
    DesktopAnalyticsBridgeService analyticsBridge,
    HttpContext context,
    CancellationToken ct) =>
    {
        if (string.IsNullOrWhiteSpace(request.HeadId)
            || string.IsNullOrWhiteSpace(request.EventName)
            || string.IsNullOrWhiteSpace(request.Surface)
            || string.IsNullOrWhiteSpace(request.ReleaseVersion)
            || string.IsNullOrWhiteSpace(request.ReleaseChannel))
        {
            return Results.BadRequest(new ProblemDetails
            {
                Title = "Desktop analytics validation failed.",
                Type = "https://chummer.run/problems/desktop-analytics-validation",
                Status = StatusCodes.Status400BadRequest,
                Detail = "Desktop analytics requests require head, event, surface, and release metadata."
            });
        }

        DesktopAnalyticsTrackResult result = await analyticsBridge.TrackAsync(
            request,
            context.Connection.RemoteIpAddress?.ToString(),
            context.Request.Headers.UserAgent.ToString(),
            ct);

        if (!result.Accepted)
        {
            if (result.Status.StartsWith("provider_http_", StringComparison.Ordinal)
                || result.Status == "provider_error")
            {
                return Results.Json(result, statusCode: StatusCodes.Status502BadGateway);
            }

            if (result.Status == "provider_not_configured")
            {
                return Results.Json(result, statusCode: StatusCodes.Status503ServiceUnavailable);
            }

            return Results.BadRequest(result);
        }

        return Results.Accepted(value: result);
    })
    .WithMetadata(new RequestSizeLimitAttribute(DesktopAnalyticsBridgeService.MaxRequestBodyBytes));
app.MapGet("/openapi/", GetSelfHostedDocs);

app.MapControllers();

app.Run();

static bool RequiresNoStoreHeaders(PathString path)
{
    return path.StartsWithSegments("/downloads/release-upload", StringComparison.OrdinalIgnoreCase)
        || IsLegacyMacReleaseBootstrapArtifactPath(path)
        || IsPublicVideoMediaPath(path)
        || path.StartsWithSegments("/downloads/proof/windows", StringComparison.OrdinalIgnoreCase)
        || path.StartsWithSegments("/downloads/aur-packages.json", StringComparison.OrdinalIgnoreCase)
        || path.StartsWithSegments("/ledger/newsroom", StringComparison.OrdinalIgnoreCase)
        || path.StartsWithSegments("/downloads/file", StringComparison.OrdinalIgnoreCase)
        || path.StartsWithSegments("/downloads/files", StringComparison.OrdinalIgnoreCase)
        || path.StartsWithSegments("/downloads/get", StringComparison.OrdinalIgnoreCase)
        || path.StartsWithSegments("/downloads/install", StringComparison.OrdinalIgnoreCase)
        || path.Equals("/robots.txt", StringComparison.OrdinalIgnoreCase)
        || path.Equals("/sitemap.xml", StringComparison.OrdinalIgnoreCase)
        || path.Equals("/llms.txt", StringComparison.OrdinalIgnoreCase)
        || path.Equals("/ai.txt", StringComparison.OrdinalIgnoreCase)
        || path.Value?.StartsWith("/install-", StringComparison.OrdinalIgnoreCase) == true;
}

static bool IsPublicVideoMediaPath(PathString path)
{
    string rawPath = path.Value ?? string.Empty;
    if (!rawPath.StartsWith("/media/", StringComparison.OrdinalIgnoreCase))
    {
        return false;
    }

    string extension = Path.GetExtension(rawPath);
    if (!extension.Equals(".mp4", StringComparison.OrdinalIgnoreCase)
        && !extension.Equals(".webm", StringComparison.OrdinalIgnoreCase)
        && !extension.Equals(".vtt", StringComparison.OrdinalIgnoreCase))
    {
        return false;
    }

    return path.StartsWithSegments("/media/horizons", StringComparison.OrdinalIgnoreCase)
        || path.StartsWithSegments("/media/promo", StringComparison.OrdinalIgnoreCase)
        || path.StartsWithSegments("/media/ledger/factions", StringComparison.OrdinalIgnoreCase)
        || path.StartsWithSegments("/media/ledger/globe", StringComparison.OrdinalIgnoreCase)
        || path.StartsWithSegments("/media/ledger/newsreels", StringComparison.OrdinalIgnoreCase)
        || path.StartsWithSegments("/media/ledger/tours", StringComparison.OrdinalIgnoreCase);
}

static string ResolveRobotsPolicy(PathString path)
{
    return IsIndexablePublicPath(path) ? PublicIndexRobotsPolicy : NoIndexRobotsPolicy;
}

static bool IsIndexablePublicPath(PathString path)
{
    string rawPath = path.Value ?? string.Empty;
    bool newsroomEpisodePath = rawPath.StartsWith("/ledger/newsroom/", StringComparison.OrdinalIgnoreCase)
        && !rawPath.EndsWith("/transcript", StringComparison.OrdinalIgnoreCase)
        && !rawPath.EndsWith("/receipts", StringComparison.OrdinalIgnoreCase);

    if (path.Equals("/", StringComparison.OrdinalIgnoreCase))
    {
        return true;
    }

    return path.Equals("/downloads", StringComparison.OrdinalIgnoreCase)
        || path.Equals("/status", StringComparison.OrdinalIgnoreCase)
        || path.Equals("/now", StringComparison.OrdinalIgnoreCase)
        || path.Equals("/participate", StringComparison.OrdinalIgnoreCase)
        || path.Equals("/changelog", StringComparison.OrdinalIgnoreCase)
        || path.Equals("/what-is-chummer", StringComparison.OrdinalIgnoreCase)
        || path.Equals("/help", StringComparison.OrdinalIgnoreCase)
        || path.Equals("/faq", StringComparison.OrdinalIgnoreCase)
        || path.Equals("/contact", StringComparison.OrdinalIgnoreCase)
        || path.Equals("/privacy", StringComparison.OrdinalIgnoreCase)
        || path.Equals("/terms", StringComparison.OrdinalIgnoreCase)
        || path.Equals("/ledger", StringComparison.OrdinalIgnoreCase)
        || path.Equals("/ledger/map", StringComparison.OrdinalIgnoreCase)
        || path.Equals("/ledger/factions", StringComparison.OrdinalIgnoreCase)
        || path.Equals("/ledger/newsroom", StringComparison.OrdinalIgnoreCase)
        || newsroomEpisodePath
        || path.Equals("/robots.txt", StringComparison.OrdinalIgnoreCase)
        || path.Equals("/sitemap.xml", StringComparison.OrdinalIgnoreCase)
        || path.Equals("/llms.txt", StringComparison.OrdinalIgnoreCase);
}

static bool IsLegacyMacReleaseBootstrapArtifactPath(PathString path)
{
    return path.Equals("/artifacts/mac-codex-release-pipeline/bootstrap.sh", StringComparison.OrdinalIgnoreCase);
}

static string ResolveHubContentRoot()
{
    string currentDirectory = Directory.GetCurrentDirectory();
    if (Directory.Exists(Path.Combine(currentDirectory, "wwwroot")))
    {
        return currentDirectory;
    }

    string baseDirectory = AppContext.BaseDirectory;
    string? candidate = TryFindHubProjectRoot(baseDirectory);
    if (!string.IsNullOrWhiteSpace(candidate))
    {
        return candidate;
    }

    candidate = TryFindHubProjectRoot(currentDirectory);
    if (!string.IsNullOrWhiteSpace(candidate))
    {
        return candidate;
    }

    return currentDirectory;
}

static string? TryFindHubProjectRoot(string startPath)
{
    var directory = new DirectoryInfo(Path.GetFullPath(startPath));
    while (directory is not null)
    {
        string wwwrootPath = Path.Combine(directory.FullName, "wwwroot");
        string projectFilePath = Path.Combine(directory.FullName, "Chummer.Run.Api.csproj");
        if (Directory.Exists(wwwrootPath) && File.Exists(projectFilePath))
        {
            return directory.FullName;
        }

        directory = directory.Parent;
    }

    return null;
}

static string[] GetCsvValues(string? value)
{
    return string.IsNullOrWhiteSpace(value)
        ? Array.Empty<string>()
        : value.Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
}

async Task ProxyRybbitAsync(HttpContext context)
{
    string origin = (context.RequestServices.GetRequiredService<IConfiguration>()["RYBBIT_CHUMMER_RUN_SCRIPT_ORIGIN"] ?? string.Empty).Trim().TrimEnd('/');
    if (!Uri.TryCreate(origin, UriKind.Absolute, out Uri? parsedOrigin)
        || parsedOrigin.Scheme != Uri.UriSchemeHttps)
    {
        context.Response.StatusCode = StatusCodes.Status404NotFound;
        return;
    }

    string proxyPath = context.Request.RouteValues.TryGetValue("proxyPath", out object? routeValue)
        ? Convert.ToString(routeValue) ?? string.Empty
        : string.Empty;
    string? normalizedProxyPath = RybbitProxyPolicy.NormalizeProxyPath(proxyPath);
    if (normalizedProxyPath is null)
    {
        context.Response.StatusCode = StatusCodes.Status400BadRequest;
        return;
    }

    string targetUrl = $"{parsedOrigin.GetLeftPart(UriPartial.Authority)}/api/{normalizedProxyPath}{context.Request.QueryString}";

    using var outbound = new HttpRequestMessage(new HttpMethod(context.Request.Method), targetUrl);
    if (context.Request.ContentLength is > 0 || context.Request.Headers.ContainsKey("Transfer-Encoding"))
    {
        outbound.Content = new StreamContent(context.Request.Body);
        if (!string.IsNullOrWhiteSpace(context.Request.ContentType))
        {
            outbound.Content.Headers.TryAddWithoutValidation("Content-Type", context.Request.ContentType);
        }
    }

    foreach (var header in context.Request.Headers)
    {
        string key = header.Key;
        if (!RybbitProxyPolicy.ShouldForwardRequestHeader(key))
        {
            continue;
        }

        string[] values = header.Value
            .Where(static value => value is not null)
            .Select(static value => value!)
            .ToArray();
        if (!outbound.Headers.TryAddWithoutValidation(key, values) && outbound.Content is not null)
        {
            outbound.Content.Headers.TryAddWithoutValidation(key, values);
        }
    }

    HttpClient client = context.RequestServices.GetRequiredService<IHttpClientFactory>().CreateClient("RybbitProxy");
    using HttpResponseMessage response = await client.SendAsync(outbound, HttpCompletionOption.ResponseHeadersRead, context.RequestAborted);
    Stream responseStream = await response.Content.ReadAsStreamAsync(context.RequestAborted);
    foreach (var header in response.Headers)
    {
        if (RybbitProxyPolicy.ShouldForwardResponseHeader(header.Key))
        {
            context.Response.Headers[header.Key] = header.Value.ToArray()!;
        }
    }

    foreach (var header in response.Content.Headers)
    {
        if (RybbitProxyPolicy.ShouldForwardResponseHeader(header.Key))
        {
            context.Response.Headers[header.Key] = header.Value.ToArray()!;
        }
    }

    context.Response.Headers.Remove("transfer-encoding");
    context.Response.StatusCode = (int)response.StatusCode;
    await responseStream.CopyToAsync(context.Response.Body, context.RequestAborted);
}

static bool HasHttpsListenerConfiguration(IConfiguration configuration)
{
    var urls = configuration["ASPNETCORE_URLS"] ?? configuration["URLS"] ?? string.Empty;
    foreach (var url in urls.Split(';', StringSplitOptions.TrimEntries | StringSplitOptions.RemoveEmptyEntries))
    {
        if (url.StartsWith("https://", StringComparison.OrdinalIgnoreCase))
        {
            return true;
        }
    }

    return !string.IsNullOrWhiteSpace(configuration["HTTPS_PORTS"]);
}

static IResult GetSelfHostedDocs()
{
    const string html = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Chummer API Docs</title>
</head>
<body>
  <main>
    <h1>Self-hosted OpenAPI explorer</h1>
    <p>Chummer Hub exposes first-party health, release, account, campaign, support, and public information routes from this host.</p>
    <ul>
      <li><a href="/api/health">Health JSON</a></li>
      <li><a href="/downloads/releases.json">Release details</a></li>
      <li><a href="/downloads/RELEASE_CHANNEL.generated.json">Current release data</a></li>
      <li><a href="/status">Release status</a></li>
    </ul>
  </main>
</body>
</html>
""";

    return Results.Content(html, "text/html; charset=utf-8");
}
