using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Microsoft.AspNetCore.Mvc;

var builder = WebApplication.CreateBuilder(args);

// Add services to the container.

builder.Services.AddProblemDetails();
builder.Services
    .AddControllers()
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
builder.Services.AddHttpClient<FleetBridgeService>();
builder.Services.AddHttpClient<HubIdentityClient>();
builder.Services.AddSingleton<CommunityStore>();
builder.Services.AddSingleton<PublicLandingService>();
builder.Services.AddSingleton<FleetReceiptVerifier>();
builder.Services.AddSingleton<AccountService>();
builder.Services.AddSingleton<IdentityLinkService>();
builder.Services.AddSingleton<GroupService>();
builder.Services.AddSingleton<RewardService>();
builder.Services.AddSingleton<EntitlementService>();
builder.Services.AddSingleton<LeaderboardService>();
builder.Services.AddSingleton<LedgerService>();
builder.Services.AddScoped<BoostSessionService>();

var app = builder.Build();

// Configure the HTTP request pipeline.

app.UseExceptionHandler();
app.UseHttpsRedirection();

app.UseAuthorization();

app.MapControllers();

app.Run();
