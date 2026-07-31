using Chummer.Run.Api;
using Microsoft.Extensions.Configuration;
using Xunit;

namespace Chummer.Tests;

public sealed class HubMetricsExportOptionsTests
{
    [Fact]
    public void FromConfiguration_disables_export_when_no_otlp_endpoint_is_configured()
    {
        IConfiguration configuration = new ConfigurationBuilder().Build();

        HubMetricsExportOptions options = HubMetricsExportOptions.FromConfiguration(configuration);

        Assert.False(options.Enabled);
        Assert.Null(options.Endpoint);
    }

    [Fact]
    public void FromConfiguration_accepts_the_governed_prometheus_otlp_binding()
    {
        IConfiguration configuration = BuildConfiguration(new Dictionary<string, string?>
        {
            [HubMetricsExportOptions.EndpointConfigurationKey] = "http://chummer-observability-prometheus:9090/api/v1/otlp",
            [HubMetricsExportOptions.ProtocolConfigurationKey] = "http/protobuf",
            [HubMetricsExportOptions.ExportIntervalConfigurationKey] = "15000",
            [HubMetricsExportOptions.ServiceNameConfigurationKey] = "chummer.run.api"
        });

        HubMetricsExportOptions options = HubMetricsExportOptions.FromConfiguration(configuration);

        Assert.True(options.Enabled);
        Assert.Equal(
            new Uri("http://chummer-observability-prometheus:9090/api/v1/otlp"),
            options.Endpoint);
        Assert.Equal(
            new Uri("http://chummer-observability-prometheus:9090/api/v1/otlp/v1/metrics"),
            options.MetricsSignalEndpoint);
        Assert.Equal("http/protobuf", options.Protocol);
        Assert.Equal(15_000, options.ExportIntervalMilliseconds);
        Assert.Equal("chummer.run.api", options.ServiceName);
    }

    [Theory]
    [InlineData("grpc", "15000")]
    [InlineData("http/protobuf", "999")]
    [InlineData("http/protobuf", "300001")]
    public void FromConfiguration_rejects_unsupported_transport_or_export_interval(
        string protocol,
        string interval)
    {
        IConfiguration configuration = BuildConfiguration(new Dictionary<string, string?>
        {
            [HubMetricsExportOptions.EndpointConfigurationKey] = "http://chummer-observability-prometheus:9090/api/v1/otlp",
            [HubMetricsExportOptions.ProtocolConfigurationKey] = protocol,
            [HubMetricsExportOptions.ExportIntervalConfigurationKey] = interval
        });

        Assert.Throws<InvalidOperationException>(
            () => HubMetricsExportOptions.FromConfiguration(configuration));
    }

    [Theory]
    [InlineData("not-a-uri")]
    [InlineData("ftp://monitor.example.test/otlp")]
    [InlineData("https://user:password@monitor.example.test/otlp")]
    [InlineData("https://monitor.example.test/otlp?private=value")]
    public void FromConfiguration_rejects_unsafe_or_non_http_endpoints(string endpoint)
    {
        IConfiguration configuration = BuildConfiguration(new Dictionary<string, string?>
        {
            [HubMetricsExportOptions.EndpointConfigurationKey] = endpoint
        });

        Assert.Throws<InvalidOperationException>(
            () => HubMetricsExportOptions.FromConfiguration(configuration));
    }

    private static IConfiguration BuildConfiguration(
        IReadOnlyDictionary<string, string?> values)
        => new ConfigurationBuilder()
            .AddInMemoryCollection(values)
            .Build();
}
