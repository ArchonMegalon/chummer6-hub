namespace Chummer.Run.Api;

internal static class HubRequestObservabilityExtensions
{
    public static WebApplicationBuilder AddHubRequestObservability(this WebApplicationBuilder builder)
    {
        builder.Services.AddSingleton(HubRequestObservabilityOptions.FromConfiguration(builder.Configuration));
        return builder;
    }

    public static WebApplication UseHubRequestObservability(this WebApplication app)
    {
        app.UseMiddleware<HubRequestObservabilityMiddleware>();
        return app;
    }
}
