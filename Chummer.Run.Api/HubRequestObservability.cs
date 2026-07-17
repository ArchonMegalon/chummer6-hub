using System.Diagnostics;
using System.Diagnostics.Metrics;
using Microsoft.Extensions.Configuration;

namespace Chummer.Run.Api;

public sealed record HubRequestObservabilityOptions
{
    public string CorrelationHeaderName { get; init; } = "X-Chummer-Correlation-Id";

    public static HubRequestObservabilityOptions FromConfiguration(IConfiguration configuration)
        => new()
        {
            CorrelationHeaderName = string.IsNullOrWhiteSpace(configuration["CHUMMER_OBSERVABILITY_CORRELATION_HEADER"])
                ? "X-Chummer-Correlation-Id"
                : configuration["CHUMMER_OBSERVABILITY_CORRELATION_HEADER"]!.Trim()
        };
}

public static class HubRequestObservability
{
    public const string CorrelationItemKey = "chummer.observability.correlation_id";
    public const string MeterName = "Chummer.Run.Api.Requests";
    public const string ActivitySourceName = "Chummer.Run.Api.Requests";
    public const string MetricRouteFallback = "__unmatched__";
    public const string MetricMethodFallback = "OTHER";

    public static readonly ActivitySource ActivitySource = new(ActivitySourceName);
    public static readonly Meter Meter = new(MeterName);
    public static readonly Counter<long> RequestsStarted = Meter.CreateCounter<long>("chummer.run.api.requests.started");
    public static readonly Counter<long> RequestsCompleted = Meter.CreateCounter<long>("chummer.run.api.requests.completed");
    public static readonly Histogram<double> RequestDurationMs = Meter.CreateHistogram<double>("chummer.run.api.requests.duration.ms");
}
