using Chummer.Run.AI.Services.Gateway;
using Chummer.Play.Contracts.Gateway;
using Microsoft.Extensions.Configuration;
using Xunit;

namespace Chummer.Tests;

public sealed class BrowserActGatewaySafetyTests
{
    [Theory]
    [InlineData("AiGateway:Providers:BrowserAct:ProxyUrl")]
    [InlineData("AiGateway:Providers:BrowserAct:ProxyRotation")]
    [InlineData("AiGateway:Providers:BrowserAct:RefreshCredentials")]
    [InlineData("AiGateway:Providers:BrowserAct:RefreshCredits")]
    [InlineData("AiGateway:Providers:BrowserAct:OneMinAiCreditRefresh")]
    [InlineData("Providers:BrowserAct:ProxyList")]
    public void BrowserAct_rejects_proxy_or_credit_refresh_configuration(string key)
    {
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["AiGateway:Providers:BrowserAct:Enabled"] = "true",
                [key] = "configured"
            })
            .Build();

        InvalidOperationException ex = Assert.Throws<InvalidOperationException>(() =>
            new BrowserActGatewayAdapter(
                new StaticHttpClientFactory(new HttpClient(new StubHandler(_ => new HttpResponseMessage()))),
                configuration));

        Assert.Contains("proxy rotation", ex.Message, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("credit refresh", ex.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void BrowserAct_allows_bounded_capture_without_proxy_or_credit_refresh()
    {
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["AiGateway:Providers:BrowserAct:Enabled"] = "true"
            })
            .Build();

        var adapter = new BrowserActGatewayAdapter(
            new StaticHttpClientFactory(new HttpClient(new StubHandler(_ => new HttpResponseMessage()))),
            configuration);

        Assert.True(adapter.Enabled);
        Assert.Equal(AiProvider.BrowserAct, adapter.Provider);
    }
}
