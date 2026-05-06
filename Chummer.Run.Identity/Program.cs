using Chummer.Run.Identity.Services;

var builder = WebApplication.CreateBuilder(args);
var enableHttpsRedirection = builder.Configuration.GetValue("IDENTITY_ENABLE_HTTPS_REDIRECTION", true);
var hasHttpsListenerConfiguration = HasHttpsListenerConfiguration(builder.Configuration);

// Add services to the container.

builder.Services.AddControllers();
builder.Services.AddSingleton<IIdentityEmailDeliveryService, IdentityEmailDeliveryService>();
builder.Services.AddSingleton<IIdentityAccessService, IdentityAccessService>();

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
