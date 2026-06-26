using Chummer.Contracts.Presentation;
using Chummer.Run.Api.Services;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class DesktopAnalyticsBridgeServiceTests
{
    [Fact]
    public async Task TrackAsync_RejectsReservedPropertyKeys()
    {
        DesktopAnalyticsBridgeService service = CreateService();
        DesktopAnalyticsTrackRequest request = CreateRequest(new Dictionary<string, string>
        {
            ["surface"] = "spoofed"
        });

        DesktopAnalyticsTrackResult result = await service.TrackAsync(request, "127.0.0.1", "test-agent", CancellationToken.None);

        Assert.False(result.Accepted);
        Assert.False(result.Forwarded);
        Assert.Equal("property_key_reserved", result.Status);
    }

    [Fact]
    public async Task TrackAsync_RejectsExcessivePropertyCounts()
    {
        DesktopAnalyticsBridgeService service = CreateService();
        Dictionary<string, string> properties = Enumerable.Range(0, DesktopAnalyticsBridgeService.MaxPropertyCount + 1)
            .ToDictionary(index => $"key{index}", index => $"value{index}", StringComparer.Ordinal);

        DesktopAnalyticsTrackResult result = await service.TrackAsync(
            CreateRequest(properties),
            "127.0.0.1",
            "test-agent",
            CancellationToken.None);

        Assert.False(result.Accepted);
        Assert.Equal("properties_limit_exceeded", result.Status);
    }

    [Fact]
    public async Task TrackAsync_RejectsOversizedPropertyValues()
    {
        DesktopAnalyticsBridgeService service = CreateService();
        DesktopAnalyticsTrackRequest request = CreateRequest(new Dictionary<string, string>
        {
            ["detail"] = new string('x', DesktopAnalyticsBridgeService.MaxPropertyValueLength + 1)
        });

        DesktopAnalyticsTrackResult result = await service.TrackAsync(request, "127.0.0.1", "test-agent", CancellationToken.None);

        Assert.False(result.Accepted);
        Assert.Equal("property_value_invalid", result.Status);
    }

    [Fact]
    public async Task TrackAsync_RejectsOversizedHeadIds()
    {
        DesktopAnalyticsBridgeService service = CreateService();
        DesktopAnalyticsTrackRequest request = CreateRequest(headId: new string('h', DesktopAnalyticsBridgeService.MaxHeadIdLength + 1));

        DesktopAnalyticsTrackResult result = await service.TrackAsync(request, "127.0.0.1", "test-agent", CancellationToken.None);

        Assert.False(result.Accepted);
        Assert.Equal("head_id_invalid", result.Status);
    }

    private static DesktopAnalyticsBridgeService CreateService()
    {
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["RYBBIT_CHUMMER_DESKTOP_SITE_ID"] = "desktop-site",
                ["RYBBIT_CHUMMER_DESKTOP_API_ORIGIN"] = "https://app.rybbit.io"
            })
            .Build();
        return new DesktopAnalyticsBridgeService(configuration, NullLogger<DesktopAnalyticsBridgeService>.Instance);
    }

    private static DesktopAnalyticsTrackRequest CreateRequest(
        IReadOnlyDictionary<string, string>? properties = null,
        string headId = "desktop-head")
        => new(
            HeadId: headId,
            EventName: "desktop_open_home",
            Surface: "home",
            ReleaseVersion: "1.2.3",
            ReleaseChannel: "stable",
            OptIn: true,
            UiMode: "desktop",
            Language: "en-US",
            OccurredAtUtc: new DateTimeOffset(2026, 6, 26, 12, 0, 0, TimeSpan.Zero),
            Properties: properties);
}
