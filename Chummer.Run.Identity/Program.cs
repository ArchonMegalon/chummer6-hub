using Chummer.Run.Identity.Services;

var builder = WebApplication.CreateBuilder(args);

// Add services to the container.

builder.Services.AddControllers();
builder.Services.AddSingleton<IIdentityEmailDeliveryService, IdentityEmailDeliveryService>();
builder.Services.AddSingleton<IIdentityAccessService, IdentityAccessService>();

var app = builder.Build();

// Configure the HTTP request pipeline.

app.UseHttpsRedirection();

app.UseAuthorization();

app.MapControllers();

app.Run();
