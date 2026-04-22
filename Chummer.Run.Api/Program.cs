using System.IO;
using System.Net;
using Chummer.Run.Api;
using Chummer.Run.Api.Services;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.AspNetCore.HttpOverrides;
using Microsoft.AspNetCore.Mvc;

var builder = WebApplication.CreateBuilder(args);
builder.AddHubApiRuntimeGuardrails();
builder.AddHubRequestObservability();

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
builder.Services.Configure<ForwardedHeadersOptions>(options =>
{
    options.ForwardedHeaders = ForwardedHeaders.XForwardedFor | ForwardedHeaders.XForwardedProto;
    options.KnownIPNetworks.Clear();
    options.KnownProxies.Clear();
});

var app = builder.Build();
app.Services.GetRequiredService<HubGoogleAuthService>().ValidateProductionReadiness();
const string SearchRobotsPolicy = "noindex, nofollow, noarchive, nosnippet, noimageindex";

// Configure the HTTP request pipeline.

app.UseExceptionHandler();
app.UseForwardedHeaders();
app.UseHttpsRedirection();
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
