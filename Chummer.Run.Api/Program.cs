using System.IO;
using System.Text.Json;
using System.Net;
using Chummer.Contracts.Presentation;
using Chummer.Run.Api;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.Services.InstallLinking;
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
var publicOriginPolicy = PublicCanonicalOriginPolicy.Create(builder.Configuration, builder.Environment);
var releaseUploadQuotaOptions = ReleaseUploadQuotaOptions.FromConfiguration(builder.Configuration);
var windowsProofUploadOptions = WindowsProofUploadOptions.FromConfiguration(builder.Configuration);
// Keep ASP.NET Core's host filter and the application policy on the same normalized,
// explicit allowlist. Program startup has already rejected wildcard/invalid values.
builder.Configuration["AllowedHosts"] = publicOriginPolicy.AllowedHostsConfiguration;
var enableHttpsRedirection = builder.Configuration.GetValue("CHUMMER_ENABLE_HTTPS_REDIRECTION", true);
var hasHttpsListenerConfiguration = HasHttpsListenerConfiguration(builder.Configuration);
PlayAuthorizationApiPolicy.ValidateStartup(builder.Configuration, builder.Environment);

// Add services to the container.

builder.Services.AddProblemDetails();
builder.Services.AddSingleton(publicOriginPolicy);
builder.Services.AddSingleton(releaseUploadQuotaOptions);
builder.Services.AddSingleton(windowsProofUploadOptions);
builder.Services.AddSingleton<WindowsProofUploadTicketService>();
builder.Services.AddSingleton<WindowsProofUploadAuthorizationEvaluator>();
builder.Services.AddSingleton<WindowsProofUploadSessionService>();
builder.Services.AddSingleton<IReleaseUploadStorageProbe, ReleaseUploadStorageProbe>();
builder.Services.AddSingleton<ReleaseUploadAuthorizationEvaluator>();
builder.Services.AddSingleton<ReleaseUploadAdmissionService>();
builder.Services.AddHostedService<ReleaseUploadExpiryJanitor>();
builder.Services.AddHostedService<ReleaseShelfInitialMigrationHostedService>();
builder.Services.AddSingleton<IReleaseShelfPublicationReadinessProbe, ReleaseShelfActivationProtocolReadinessProbe>();
builder.Services.AddSingleton<IReleaseShelfPublicationReadinessProbe, ReleaseUploadStoragePublicationReadinessProbe>();
builder.Services.AddHostedService<ReleaseShelfPublicationReadinessRefreshService>();
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

DataProtectionKeyProtectionStatus dataProtectionKeyProtection =
    DataProtectionKeyProtectionConfigurator.Configure(
        builder.Services,
        builder.Configuration,
        builder.Environment,
        dataProtectionPath);
builder.Services.AddSingleton(dataProtectionKeyProtection);
builder.Services.AddPlayAuthorizationProcessLease();
builder.Services
    .AddHubPublicGuideContext()
    .AddHubAccountsAndCommunityContext()
    .AddHubCampaignSpineContext()
    .AddHubControlAndSupportContext()
    .AddHubInstallAndOrchestrationAdapters(builder.Configuration, builder.Environment);
builder.Services.AddSingleton<HubDeepReadinessService>();
builder.Services.AddSingleton<PortalDeploymentIdentityReadinessService>();
builder.Services.AddSingleton<DesktopAnalyticsBridgeService>();
builder.Services.AddHttpClient("RybbitProxy", client =>
{
    client.Timeout = TimeSpan.FromSeconds(15);
});
builder.Services
    .AddHttpClient(PublicProxyRedirectPolicy.HttpClientName)
    .ConfigurePrimaryHttpMessageHandler(() => new HttpClientHandler
    {
        AllowAutoRedirect = false,
        UseCookies = false
    });
builder.Services.AddSingleton<PublicPlayProxyGateway>();
builder.Services.AddSingleton<IPublicPlayPrivateRouteDelegator, DenyAllPublicPlayPrivateRouteDelegator>();
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
PublicPlayProxyGateway playProjectionGateway = app.Services.GetRequiredService<PublicPlayProxyGateway>();
PublicPlayProjectionReadiness playProjectionReadiness = playProjectionGateway.GetReadiness();
if (!playProjectionReadiness.Ready)
{
    app.Logger.LogError(
        "Public Play projection readiness is {Status}: {Detail}",
        playProjectionReadiness.Status,
        playProjectionReadiness.Detail);
}
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
app.Use(async (context, next) =>
{
    if (!publicOriginPolicy.TryValidateRequest(context.Request, out string failure))
    {
        PrivateResponseCacheHeaders.Apply(context.Response.Headers);
        if (RequiresNoReferrerHeaders(context.Request.Path))
        {
            context.Response.Headers["Referrer-Policy"] = "no-referrer";
        }
        context.Response.StatusCode = StatusCodes.Status400BadRequest;
        context.Response.ContentType = "application/problem+json; charset=utf-8";
        var problem = new ProblemDetails
        {
            Title = "Invalid public host.",
            Type = "https://chummer.run/problems/invalid-public-host",
            Status = StatusCodes.Status400BadRequest,
            Detail = failure,
            Instance = $"{context.Request.Path}#{context.TraceIdentifier}"
        };
        await JsonSerializer.SerializeAsync(context.Response.Body, problem, cancellationToken: context.RequestAborted);
        return;
    }

    await next();
});
// Register private-response and indexing headers before HTTPS redirection so a
// redirect cannot bypass the account/admin cache boundary.
app.Use(async (context, next) =>
{
    bool requiresNoStore = RequiresNoStoreHeaders(context.Request.Path);
    string robotsPolicy = ResolveRobotsPolicy(context.Request.Path);
    context.Response.OnStarting(() =>
    {
        context.Response.Headers["X-Robots-Tag"] = robotsPolicy;
        if (requiresNoStore)
        {
            PrivateResponseCacheHeaders.Apply(context.Response.Headers);
        }
        if (RequiresNoReferrerHeaders(context.Request.Path))
        {
            context.Response.Headers["Referrer-Policy"] = "no-referrer";
        }
        if (IsPrivatePlayDocumentPath(context.Request.Path))
        {
            context.Response.Headers["Content-Security-Policy"] = "default-src 'none'; base-uri 'none'; connect-src 'none'; form-action 'self'; frame-ancestors 'none'; img-src 'self' data:; manifest-src 'self'; script-src 'self'; style-src 'self'; worker-src 'self'";
            context.Response.Headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=(), usb=()";
            context.Response.Headers["X-Content-Type-Options"] = "nosniff";
            context.Response.Headers["X-Frame-Options"] = "DENY";
        }

        return Task.CompletedTask;
    });

    await next();
});
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
    if (IsLegacyMacReleaseBootstrapArtifactPath(context.Request.Path))
    {
        context.Response.Redirect("/downloads/release-upload/bootstrap.sh", permanent: false);
        return;
    }

    await next();
});
app.Use(async (context, next) =>
{
    if ((HttpMethods.IsGet(context.Request.Method) || HttpMethods.IsHead(context.Request.Method))
        && TryResolveRoleAliasRedirectPath(context.Request.Path, out string? redirectPath))
    {
        PrivateResponseCacheHeaders.Apply(context.Response.Headers);
        context.Response.Headers.CacheControl = "private, no-store, no-cache, max-age=0";
        context.Response.Headers["Referrer-Policy"] = "no-referrer";
        // Role aliases are public install-entry names, never session handoff URLs.
        // Drop every query value and emit an explicit empty fragment so browsers do
        // not inherit a private fragment from the alias URL during redirection.
        context.Response.Redirect($"{redirectPath}#", permanent: false);
        return;
    }

    await next();
});
app.UseRouting();
app.UseMiddleware<PublicReleaseTruthProjectionMiddleware>();
app.UseMiddleware<WindowsProofUploadRequestGateMiddleware>();
app.UseMiddleware<ReleaseUploadRequestGateMiddleware>();
app.UsePlayAuthorizationApiGate();
app.UseHubRequestObservability();
app.UseHubApiRuntimeGuardrails();
app.UseMiddleware<InstallLinkingRequestAdmissionMiddleware>();
app.Use(async (context, next) =>
{
    if (PublicPlaySessionAccessPolicy.RequiresSessionGrant(context.Request))
    {
        IPublicPlayPrivateRouteDelegator privateRoutes = context.RequestServices
            .GetRequiredService<IPublicPlayPrivateRouteDelegator>();
        await privateRoutes.DenyAsync(context, context.RequestAborted);
        return;
    }

    await next();
});
FileExtensionContentTypeProvider contentTypeProvider = new();
contentTypeProvider.Mappings[".vtt"] = "text/vtt";
contentTypeProvider.Mappings[".webmanifest"] = "application/manifest+json";
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

app.UseWhen(
    static context => !IsGovernedReleaseStaticPath(context.Request.Path),
    staticFiles => staticFiles.UseStaticFiles(new StaticFileOptions
    {
        ContentTypeProvider = contentTypeProvider,
        OnPrepareResponse = fileContext =>
        {
            PathString requestPath = fileContext.Context.Request.Path;
            fileContext.Context.Response.Headers["X-Robots-Tag"] = ResolveRobotsPolicy(requestPath);
            if (RequiresNoStoreHeaders(requestPath))
            {
                PrivateResponseCacheHeaders.Apply(fileContext.Context.Response.Headers);
            }
            if (IsLocalPlayInstallAssetPath(requestPath))
            {
                fileContext.Context.Response.Headers["X-Content-Type-Options"] = "nosniff";
                if (requestPath.Equals("/service-worker.js", StringComparison.OrdinalIgnoreCase)
                    || requestPath.Equals("/mobile/service-worker.js", StringComparison.OrdinalIgnoreCase))
                {
                    fileContext.Context.Response.ContentType = "application/javascript; charset=utf-8";
                    fileContext.Context.Response.Headers.CacheControl = "no-cache, no-store, must-revalidate";
                }
                else
                {
                    if (requestPath.Value?.EndsWith(".js", StringComparison.OrdinalIgnoreCase) is true)
                    {
                        fileContext.Context.Response.ContentType = "application/javascript; charset=utf-8";
                    }
                    fileContext.Context.Response.Headers.CacheControl = "public, max-age=300, must-revalidate";
                }
            }
        }
    }));

app.UseWebSockets();
app.UseAuthorization();

app.MapMethods("/api/health", new[] { HttpMethods.Get, HttpMethods.Head }, () => Results.Json(new
{
    ok = true,
    service = "chummer.run.api",
    status = "pass",
    generatedAt = DateTimeOffset.UtcNow
}));
app.MapMethods("/api/ready", new[] { HttpMethods.Get, HttpMethods.Head }, (
    HubDeepReadinessService readiness,
    PublicPlayProxyGateway playGateway,
    PortalDeploymentIdentityReadinessService deploymentIdentityReadiness,
    HttpContext context) =>
{
    PrivateResponseCacheHeaders.Apply(context.Response.Headers);
    context.Response.Headers["X-Content-Type-Options"] = "nosniff";
    HubDeepReadinessReport report = readiness.Evaluate();
    PublicPlayProjectionReadiness projection = playGateway.GetReadiness();
    PortalDeploymentIdentityReadiness deploymentIdentity = deploymentIdentityReadiness.Evaluate();
    context.Response.Headers["X-Chummer-Play-Projection-Status"] = projection.Status;
    HubReadyResponse combinedReport = HubReadyResponse.Create(
        report,
        projection,
        deploymentIdentity);
    return Results.Json(
        combinedReport,
        statusCode: combinedReport.Ready
            ? StatusCodes.Status200OK
            : StatusCodes.Status503ServiceUnavailable);
});
app.MapMethods("/api/ready/play-projection", new[] { HttpMethods.Get, HttpMethods.Head }, (
    PublicPlayProxyGateway playGateway) =>
{
    PublicPlayProjectionReadiness projection = playGateway.GetReadiness();
    return Results.Json(
        projection,
        statusCode: projection.Ready
            ? StatusCodes.Status200OK
            : StatusCodes.Status503ServiceUnavailable);
});
app.MapMethods("/api/ready/publication", new[] { HttpMethods.Get, HttpMethods.Head }, async (
    HubDeepReadinessService readiness,
    CancellationToken cancellationToken) =>
{
    ReleaseShelfPublicationReadinessState publication =
        await readiness.EvaluatePublicationReadinessAsync(cancellationToken);
    return Results.Json(
        publication,
        statusCode: publication.Ready
            ? StatusCodes.Status200OK
            : StatusCodes.Status503ServiceUnavailable);
});
app.MapGet("/downloads/release-evidence/{**path}", (
    string? path,
    PublicReleaseManifestService releases,
    HttpContext context) =>
{
    ReleaseShelfSnapshot snapshot = releases.CaptureShelfSnapshot();
    if (!string.IsNullOrWhiteSpace(snapshot.GenerationId))
    {
        context.Response.Headers["X-Chummer-Release-Generation"] = snapshot.GenerationId;
    }

    if (!snapshot.IsLegacy)
    {
        ReleaseShelfVerifiedFile? verified = snapshot.OpenVerifiedFile($"release-evidence/{path}");
        return verified is null
            ? Results.NotFound()
            : Results.Stream(verified.Stream, "application/json; charset=utf-8");
    }

    string? filePath = releases.ResolveReleaseEvidenceFilePath(snapshot, path);
    return filePath is null
        ? Results.NotFound()
        : Results.File(filePath, "application/json; charset=utf-8");
});
app.MapGet("/downloads/g/{generationId}/release-evidence/{**path}", (
    string generationId,
    string? path,
    PublicReleaseManifestService releases,
    HttpContext context) =>
{
    try
    {
        ReleaseShelfSnapshot snapshot = releases.CaptureShelfGeneration(generationId);
        context.Response.Headers["X-Chummer-Release-Generation"] = snapshot.GenerationId;
        ReleaseShelfVerifiedFile? verified = snapshot.OpenVerifiedFile($"release-evidence/{path}");
        return verified is null
            ? Results.NotFound()
            : Results.Stream(verified.Stream, "application/json; charset=utf-8");
    }
    catch (InvalidDataException)
    {
        return Results.NotFound();
    }
    catch (InvalidOperationException)
    {
        return Results.NotFound();
    }
});
app.MapGet("/downloads/g/{generationId}/proof/{**path}", (
    string generationId,
    string? path,
    PublicReleaseManifestService releases,
    HttpContext context) =>
{
    try
    {
        ReleaseShelfSnapshot snapshot = releases.CaptureShelfGeneration(generationId);
        context.Response.Headers["X-Chummer-Release-Generation"] = snapshot.GenerationId;
        ReleaseShelfVerifiedFile? verified = snapshot.OpenVerifiedFile($"proof/{path}");
        return verified is null
            ? Results.NotFound()
            : Results.Stream(verified.Stream, "application/json; charset=utf-8");
    }
    catch (InvalidDataException)
    {
        return Results.NotFound();
    }
    catch (InvalidOperationException)
    {
        return Results.NotFound();
    }
});
app.MapGet("/downloads/g/{generationId}/startup-smoke/{**path}", (
    string generationId,
    string? path,
    PublicReleaseManifestService releases,
    HttpContext context) =>
{
    try
    {
        ReleaseShelfSnapshot snapshot = releases.CaptureShelfGeneration(generationId);
        context.Response.Headers["X-Chummer-Release-Generation"] = snapshot.GenerationId;
        ReleaseShelfVerifiedFile? verified = snapshot.OpenVerifiedFile($"startup-smoke/{path}");
        return verified is null
            ? Results.NotFound()
            : Results.Stream(verified.Stream, "application/json; charset=utf-8");
    }
    catch (InvalidDataException)
    {
        return Results.NotFound();
    }
    catch (InvalidOperationException)
    {
        return Results.NotFound();
    }
});
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
    string rawPath = path.Value ?? string.Empty;
    return rawPath.Equals("/login", StringComparison.OrdinalIgnoreCase)
        || rawPath.Equals("/signup", StringComparison.OrdinalIgnoreCase)
        || rawPath.Equals("/auth", StringComparison.OrdinalIgnoreCase)
        || rawPath.StartsWith("/auth/", StringComparison.OrdinalIgnoreCase)
        || PrivateResponseCacheHeaders.IsPrivateAccountSurface(path)
        || PrivateResponseCacheHeaders.IsPrivateAdminSurface(path)
        || path.StartsWithSegments("/downloads/release-upload", StringComparison.OrdinalIgnoreCase)
        || path.StartsWithSegments(PlayAuthorizationApiPolicy.AccountPathPrefix, StringComparison.OrdinalIgnoreCase)
        || path.StartsWithSegments(PlayAuthorizationApiPolicy.InternalPathPrefix, StringComparison.OrdinalIgnoreCase)
        || IsInstallLinkingSensitivePath(path)
        || IsLegacyMacReleaseBootstrapArtifactPath(path)
        || IsPublicVideoMediaPath(path)
        || path.Equals("/service-worker.js", StringComparison.OrdinalIgnoreCase)
        || path.Equals("/mobile/service-worker.js", StringComparison.OrdinalIgnoreCase)
        || path.Equals("/manifest.json", StringComparison.OrdinalIgnoreCase)
        || path.StartsWithSegments("/downloads/proof/windows", StringComparison.OrdinalIgnoreCase)
        || path.Equals("/downloads/releases.json", StringComparison.OrdinalIgnoreCase)
        || path.Equals("/downloads/RELEASE_CHANNEL.generated.json", StringComparison.OrdinalIgnoreCase)
        || path.StartsWithSegments("/downloads/release-evidence", StringComparison.OrdinalIgnoreCase)
        || path.StartsWithSegments("/downloads/aur-packages.json", StringComparison.OrdinalIgnoreCase)
        || path.StartsWithSegments("/downloads/g", StringComparison.OrdinalIgnoreCase)
        || path.StartsWithSegments("/ledger/newsroom", StringComparison.OrdinalIgnoreCase)
        || path.StartsWithSegments("/downloads/file", StringComparison.OrdinalIgnoreCase)
        || path.StartsWithSegments("/downloads/files", StringComparison.OrdinalIgnoreCase)
        || path.StartsWithSegments("/downloads/get", StringComparison.OrdinalIgnoreCase)
        || path.StartsWithSegments("/downloads/install", StringComparison.OrdinalIgnoreCase)
        || path.Equals("/robots.txt", StringComparison.OrdinalIgnoreCase)
        || path.Equals("/sitemap.xml", StringComparison.OrdinalIgnoreCase)
        || path.Equals("/llms.txt", StringComparison.OrdinalIgnoreCase)
        || path.Equals("/ai.txt", StringComparison.OrdinalIgnoreCase)
        || IsPrivatePlayDocumentPath(path)
        || path.Value?.StartsWith("/install-", StringComparison.OrdinalIgnoreCase) == true;
}

static bool RequiresNoReferrerHeaders(PathString path)
    => IsPrivatePlayDocumentPath(path)
        || IsInstallLinkingSensitivePath(path)
        || PrivateResponseCacheHeaders.IsPrivateAccountSurface(path)
        || PrivateResponseCacheHeaders.IsPrivateAdminSurface(path)
        || path.StartsWithSegments("/downloads/g", StringComparison.OrdinalIgnoreCase);

static bool IsGovernedReleaseStaticPath(PathString path)
{
    return path.Equals("/downloads/current.json", StringComparison.OrdinalIgnoreCase)
        || path.Equals("/downloads/releases.json", StringComparison.OrdinalIgnoreCase)
        || path.Equals("/downloads/RELEASE_CHANNEL.generated.json", StringComparison.OrdinalIgnoreCase)
        || path.Equals("/downloads/aur-packages.json", StringComparison.OrdinalIgnoreCase)
        || path.StartsWithSegments("/downloads/g", StringComparison.OrdinalIgnoreCase)
        || path.StartsWithSegments("/downloads/files", StringComparison.OrdinalIgnoreCase)
        || path.StartsWithSegments("/downloads/file", StringComparison.OrdinalIgnoreCase)
        || path.StartsWithSegments("/downloads/get", StringComparison.OrdinalIgnoreCase)
        || path.StartsWithSegments("/downloads/install", StringComparison.OrdinalIgnoreCase)
        || path.StartsWithSegments("/downloads/proof", StringComparison.OrdinalIgnoreCase)
        || path.StartsWithSegments("/downloads/startup-smoke", StringComparison.OrdinalIgnoreCase)
        || path.StartsWithSegments("/downloads/release-evidence", StringComparison.OrdinalIgnoreCase)
        || path.StartsWithSegments("/downloads/aur", StringComparison.OrdinalIgnoreCase);
}

static bool IsPrivatePlayDocumentPath(PathString path)
{
    string value = (path.Value ?? string.Empty).TrimEnd('/');
    return value.Equals("/mobile", StringComparison.OrdinalIgnoreCase)
        || value.Equals("/mobile/player", StringComparison.OrdinalIgnoreCase)
        || value.Equals("/mobile/gm", StringComparison.OrdinalIgnoreCase)
        || value.Equals("/mobile/observer", StringComparison.OrdinalIgnoreCase);
}

static bool IsInstallLinkingSensitivePath(PathString path)
{
    return path.StartsWithSegments("/api/v1/install-linking", StringComparison.OrdinalIgnoreCase)
        || path.Equals("/account/access/install-link", StringComparison.OrdinalIgnoreCase);
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

static bool TryResolveRoleAliasRedirectPath(PathString path, out string redirectPath)
{
    if (path.Equals("/player", StringComparison.OrdinalIgnoreCase)
        || path.Equals("/jammer", StringComparison.OrdinalIgnoreCase))
    {
        redirectPath = "/mobile/player";
        return true;
    }

    if (path.Equals("/gm", StringComparison.OrdinalIgnoreCase))
    {
        redirectPath = "/mobile/gm";
        return true;
    }

    if (path.Equals("/observer", StringComparison.OrdinalIgnoreCase))
    {
        redirectPath = "/mobile/observer";
        return true;
    }

    redirectPath = string.Empty;
    return false;
}

static bool IsLocalPlayInstallAssetPath(PathString path)
{
    string value = path.Value ?? string.Empty;
    return value.Equals("/js/mobile-app-handoff.js", StringComparison.OrdinalIgnoreCase)
        || value.Equals("/mobile-install-shell.js", StringComparison.OrdinalIgnoreCase)
        || value.Equals("/mobile.css", StringComparison.OrdinalIgnoreCase)
        || value.Equals("/service-worker.js", StringComparison.OrdinalIgnoreCase)
        || value.Equals("/mobile/service-worker.js", StringComparison.OrdinalIgnoreCase)
        || value.Equals("/manifest.webmanifest", StringComparison.OrdinalIgnoreCase)
        || value.Equals("/manifest.play.webmanifest", StringComparison.OrdinalIgnoreCase)
        || value.Equals("/manifest.player.webmanifest", StringComparison.OrdinalIgnoreCase)
        || value.Equals("/manifest.gm.webmanifest", StringComparison.OrdinalIgnoreCase)
        || value.Equals("/manifest.observer.webmanifest", StringComparison.OrdinalIgnoreCase)
        || value.Equals("/icons/icon-192.svg", StringComparison.OrdinalIgnoreCase)
        || value.Equals("/icons/icon-512.svg", StringComparison.OrdinalIgnoreCase)
        || value.Equals("/icons/icon-192.png", StringComparison.OrdinalIgnoreCase)
        || value.Equals("/icons/icon-512.png", StringComparison.OrdinalIgnoreCase);
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
