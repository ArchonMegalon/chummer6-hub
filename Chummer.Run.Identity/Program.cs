using Chummer.Run.Identity.Services;
using Chummer.Storage.Teable;

var builder = WebApplication.CreateBuilder(args);
var enableHttpsRedirection = builder.Configuration.GetValue("IDENTITY_ENABLE_HTTPS_REDIRECTION", true);
var hasHttpsListenerConfiguration = HasHttpsListenerConfiguration(builder.Configuration);

// Add services to the container.

builder.Services.AddControllers();
builder.Services.AddSingleton<IIdentityEmailDeliveryService, IdentityEmailDeliveryService>();
if (builder.Configuration["CHUMMER_IDENTITY_STORAGE_PROVIDER"]?.Trim() == "teable")
{
    builder.Services.AddSingleton(_ => TeableRevisionStore.OpenFromPrivateTokenFile(
        new Uri(builder.Configuration["CHUMMER_TEABLE_ORIGIN"] ?? "https://app.teable.ai/"),
        builder.Configuration["CHUMMER_TEABLE_TABLE_ID"] ?? throw new InvalidOperationException("Teable table is required."),
        builder.Configuration["CHUMMER_TEABLE_TOKEN_FILE"] ?? throw new InvalidOperationException("Private Teable token file is required.")));
}
builder.Services.AddSingleton<IdentityAccessService>();
builder.Services.AddSingleton<IIdentityAccessService>(provider => provider.GetRequiredService<IdentityAccessService>());

var app = builder.Build();

// Configure the HTTP request pipeline.

if (enableHttpsRedirection && hasHttpsListenerConfiguration)
{
    app.UseHttpsRedirection();
}
else if (enableHttpsRedirection)
{
    app.Logger.LogWarning("IDENTITY_ENABLE_HTTPS_REDIRECTION is enabled, but the identity service has no HTTPS listener configured. Skipping HTTPS redirection.");
}

app.UseAuthorization();

app.MapControllers();
app.MapMethods("/health", [HttpMethods.Get, HttpMethods.Head], (IdentityAccessService identity) =>
{
    bool ready = identity.IsStorageReady();
    return Results.Json(new
    {
        ok = ready,
        service = "chummer.run.identity",
        status = ready ? "ready" : "storage_unavailable",
        generatedAt = DateTimeOffset.UtcNow
    }, statusCode: ready ? StatusCodes.Status200OK : StatusCodes.Status503ServiceUnavailable);
});

app.Run();

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
