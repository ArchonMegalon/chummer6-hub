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

public sealed record HubMetricsExportOptions
{
    public const string EndpointConfigurationKey = "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT";
    public const string ProtocolConfigurationKey = "OTEL_EXPORTER_OTLP_PROTOCOL";
    public const string ExportIntervalConfigurationKey = "OTEL_METRIC_EXPORT_INTERVAL";
    public const string ServiceNameConfigurationKey = "OTEL_SERVICE_NAME";
    public const string RequiredProtocol = "http/protobuf";
    public const int DefaultExportIntervalMilliseconds = 15_000;
    public const int MinimumExportIntervalMilliseconds = 1_000;
    public const int MaximumExportIntervalMilliseconds = 300_000;

    public bool Enabled { get; init; }
    public Uri? Endpoint { get; init; }
    public string Protocol { get; init; } = RequiredProtocol;
    public int ExportIntervalMilliseconds { get; init; } = DefaultExportIntervalMilliseconds;
    public string ServiceName { get; init; } = "chummer.run.api";

    public Uri MetricsSignalEndpoint
    {
        get
        {
            if (!Enabled || Endpoint is null)
            {
                throw new InvalidOperationException("The OTLP metrics signal endpoint is unavailable while export is disabled.");
            }

            UriBuilder signalEndpoint = new(Endpoint)
            {
                Path = $"{Endpoint.AbsolutePath.TrimEnd('/')}/v1/metrics"
            };
            return signalEndpoint.Uri;
        }
    }

    public static HubMetricsExportOptions FromConfiguration(IConfiguration configuration)
    {
        string endpointValue = (configuration[EndpointConfigurationKey] ?? string.Empty).Trim();
        if (endpointValue.Length == 0)
        {
            return new HubMetricsExportOptions();
        }

        if (!Uri.TryCreate(endpointValue, UriKind.Absolute, out Uri? endpoint)
            || (endpoint.Scheme != Uri.UriSchemeHttp && endpoint.Scheme != Uri.UriSchemeHttps)
            || !string.IsNullOrEmpty(endpoint.UserInfo)
            || !string.IsNullOrEmpty(endpoint.Query)
            || !string.IsNullOrEmpty(endpoint.Fragment))
        {
            throw new InvalidOperationException(
                $"{EndpointConfigurationKey} must be an absolute HTTP(S) OTLP metrics base endpoint without credentials, query, or fragment.");
        }

        string protocol = (configuration[ProtocolConfigurationKey] ?? RequiredProtocol).Trim().ToLowerInvariant();
        if (!string.Equals(protocol, RequiredProtocol, StringComparison.Ordinal))
        {
            throw new InvalidOperationException(
                $"{ProtocolConfigurationKey} must be {RequiredProtocol} for the governed Prometheus OTLP receiver.");
        }

        string intervalValue = (configuration[ExportIntervalConfigurationKey] ?? string.Empty).Trim();
        int exportIntervalMilliseconds = DefaultExportIntervalMilliseconds;
        if (intervalValue.Length > 0
            && (!int.TryParse(
                    intervalValue,
                    System.Globalization.NumberStyles.None,
                    System.Globalization.CultureInfo.InvariantCulture,
                    out exportIntervalMilliseconds)
                || exportIntervalMilliseconds < MinimumExportIntervalMilliseconds
                || exportIntervalMilliseconds > MaximumExportIntervalMilliseconds))
        {
            throw new InvalidOperationException(
                $"{ExportIntervalConfigurationKey} must be between {MinimumExportIntervalMilliseconds} and {MaximumExportIntervalMilliseconds} milliseconds.");
        }

        string serviceName = (configuration[ServiceNameConfigurationKey] ?? "chummer.run.api").Trim();
        if (serviceName.Length == 0 || serviceName.Length > 128)
        {
            throw new InvalidOperationException(
                $"{ServiceNameConfigurationKey} must contain between 1 and 128 characters.");
        }

        return new HubMetricsExportOptions
        {
            Enabled = true,
            Endpoint = endpoint,
            Protocol = protocol,
            ExportIntervalMilliseconds = exportIntervalMilliseconds,
            ServiceName = serviceName
        };
    }
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
