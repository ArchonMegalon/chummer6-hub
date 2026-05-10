using System.IO;
using System.Text.Json;
using System.Net;
using Chummer.Run.Api;
using Chummer.Run.Api.Services;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.AspNetCore.HttpOverrides;
using Microsoft.AspNetCore.Mvc;

var builder = WebApplication.CreateBuilder(args);
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
var dataProtectionPath = builder.Configuration["CHUMMER_DATA_PROTECTION_KEYS_PATH"];
if (string.IsNullOrWhiteSpace(dataProtectionPath))
{
    dataProtectionPath = Path.Combine(Path.GetTempPath(), "chummer-run-api", "data-protection-keys");
}

builder.Services.AddDataProtection()
    .SetApplicationName("Chummer.Run.Api")
    .PersistKeysToFileSystem(new DirectoryInfo(Path.GetFullPath(dataProtectionPath)));
builder.Services
    .AddHubPublicGuideContext()
    .AddHubAccountsAndCommunityContext()
    .AddHubCampaignSpineContext()
    .AddHubControlAndSupportContext()
    .AddHubInstallAndOrchestrationAdapters();
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
var hubGoogleAuth = app.Services.GetRequiredService<HubGoogleAuthService>();
hubGoogleAuth.ValidateProductionReadiness();
if (!hubGoogleAuth.IsConfigured())
{
    app.Logger.LogWarning("Google OIDC is not configured; Hub will start with Google sign-in surfaces disabled.");
}
const string SearchRobotsPolicy = "noindex, nofollow, noarchive, nosnippet, noimageindex";

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
    context.Response.OnStarting(() =>
    {
        context.Response.Headers["X-Robots-Tag"] = SearchRobotsPolicy;
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
app.UseStaticFiles(new StaticFileOptions
{
    OnPrepareResponse = fileContext =>
    {
        fileContext.Context.Response.Headers["X-Robots-Tag"] = SearchRobotsPolicy;
    }
});

app.UseHubRequestObservability();
app.UseHubApiRuntimeGuardrails();
app.UseAuthorization();

app.MapControllers();

app.Run();

static bool RequiresNoStoreHeaders(PathString path)
{
    return path.StartsWithSegments("/downloads/release-upload", StringComparison.OrdinalIgnoreCase)
        || IsLegacyMacReleaseBootstrapArtifactPath(path)
        || path.StartsWithSegments("/downloads/proof/windows", StringComparison.OrdinalIgnoreCase)
        || path.StartsWithSegments("/downloads/install", StringComparison.OrdinalIgnoreCase)
        || path.Value?.StartsWith("/install-", StringComparison.OrdinalIgnoreCase) == true;
}

static bool IsLegacyMacReleaseBootstrapArtifactPath(PathString path)
{
    return path.Equals("/artifacts/mac-codex-release-pipeline/bootstrap.sh", StringComparison.OrdinalIgnoreCase);
}

static string[] GetCsvValues(string? value)
{
    return string.IsNullOrWhiteSpace(value)
        ? Array.Empty<string>()
        : value.Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
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
