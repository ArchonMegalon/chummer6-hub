using OpenTelemetry.Exporter;
using OpenTelemetry.Metrics;
using OpenTelemetry.Resources;

namespace Chummer.Run.Api;

internal static class HubRequestObservabilityExtensions
{
    public static WebApplicationBuilder AddHubRequestObservability(this WebApplicationBuilder builder)
    {
        builder.Services.AddSingleton(HubRequestObservabilityOptions.FromConfiguration(builder.Configuration));
        HubMetricsExportOptions metricsExport = HubMetricsExportOptions.FromConfiguration(builder.Configuration);
        builder.Services.AddSingleton(metricsExport);
        if (metricsExport.Enabled)
        {
            builder.Services
                .AddOpenTelemetry()
                .ConfigureResource(resource => resource.AddService(metricsExport.ServiceName))
                .WithMetrics(metrics => metrics
                    .AddMeter(HubRequestObservability.MeterName)
                    .AddOtlpExporter((exporterOptions, readerOptions) =>
                    {
                        exporterOptions.Endpoint = metricsExport.MetricsSignalEndpoint;
                        exporterOptions.Protocol = OtlpExportProtocol.HttpProtobuf;
                        readerOptions.PeriodicExportingMetricReaderOptions.ExportIntervalMilliseconds =
                            metricsExport.ExportIntervalMilliseconds;
                    }));
        }

        return builder;
    }

    public static WebApplication UseHubRequestObservability(this WebApplication app)
    {
        app.UseMiddleware<HubRequestObservabilityMiddleware>();
        return app;
    }
}
