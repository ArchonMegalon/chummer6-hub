using System.IO;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.AspNetCore.Mvc;

var builder = WebApplication.CreateBuilder(args);

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
builder.Services.AddHttpClient<FleetBridgeService>();
builder.Services.AddHttpClient<HubIdentityClient>();
builder.Services.AddHttpClient<HubBrowserAuthService>();
builder.Services.AddHttpClient<HubGoogleAuthService>();
builder.Services.AddSingleton<CommunityStore>();
builder.Services.AddSingleton<PublicLandingService>();
builder.Services.AddSingleton<PublicNavigationService>();
builder.Services.AddSingleton<HubPageChromeService>();
builder.Services.AddSingleton<HubEmailLinkVerificationService>();
builder.Services.AddSingleton<PublicProgressService>();
builder.Services.AddSingleton<PublicReleaseManifestService>();
builder.Services.AddSingleton<FleetReceiptVerifier>();
builder.Services.AddSingleton<AccountService>();
builder.Services.AddSingleton<IdentityLinkService>();
builder.Services.AddSingleton<UserExperienceService>();
builder.Services.AddSingleton<GroupService>();
builder.Services.AddSingleton<RewardService>();
builder.Services.AddSingleton<EntitlementService>();
builder.Services.AddSingleton<LeaderboardService>();
builder.Services.AddSingleton<LedgerService>();
builder.Services.AddScoped<BoostSessionService>();

var app = builder.Build();
app.Services.GetRequiredService<HubGoogleAuthService>().ValidateProductionReadiness();

// Configure the HTTP request pipeline.

app.UseExceptionHandler();
app.UseHttpsRedirection();
app.UseStaticFiles();

app.UseAuthorization();

app.MapControllers();

app.Run();
