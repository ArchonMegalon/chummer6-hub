using Chummer.Run.Identity.Services;

var builder = WebApplication.CreateBuilder(args);
var enableHttpsRedirection = builder.Configuration.GetValue("IDENTITY_ENABLE_HTTPS_REDIRECTION", false);

// Add services to the container.

builder.Services.AddControllers();
builder.Services.AddSingleton<IIdentityEmailDeliveryService, IdentityEmailDeliveryService>();
builder.Services.AddSingleton<IIdentityAccessService, IdentityAccessService>();

var app = builder.Build();

// Configure the HTTP request pipeline.

if (enableHttpsRedirection)
{
    app.UseHttpsRedirection();
}

app.UseAuthorization();

app.MapControllers();

app.Run();
