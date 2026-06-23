using Chummer.Run.AI.Services.Gateway;
using Microsoft.Extensions.Configuration;
using PlayGateway = Chummer.Play.Contracts.Gateway;
using Xunit;

namespace Chummer.Tests;

public sealed class ProviderRouterTests
{
    [Fact]
    public void Resolve_UsesNewDefaultTierModels()
    {
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["AiGateway:Providers:AiMagicx:Enabled"] = "true",
                ["AiGateway:Providers:OneMinAi:Enabled"] = "true"
            })
            .Build();

        var router = new ProviderRouter(configuration);

        var standard = router.Resolve(new PlayGateway.ProviderRouteRequest(
            Purpose: "summary",
            Prompt: "hello",
            StructuredOutput: false,
            MaxTokens: 400,
            SessionId: "session-standard"));
        var complex = router.Resolve(new PlayGateway.ProviderRouteRequest(
            Purpose: "analysis",
            Prompt: "hello",
            StructuredOutput: true,
            MaxTokens: 1200,
            SessionId: "session-complex"));

        Assert.Equal("gpt-5.5", standard.SelectedModel);
        Assert.Equal("claude-opus-4.1", complex.SelectedModel);
    }

    [Fact]
    public void Resolve_AllowsTierPolicyOverridesFromConfiguration()
    {
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["AiGateway:Providers:AiMagicx:Enabled"] = "true",
                ["AiGateway:Routing:ComplexTokenThreshold"] = "900",
                ["AiGateway:Routing:Standard:SelectedModel"] = "gpt-5.5-codex",
                ["AiGateway:Routing:Standard:ReasoningEffort"] = "medium",
                ["AiGateway:Routing:Complex:SelectedModel"] = "claude-opus-4.1-thinking",
                ["AiGateway:Routing:Complex:Policy"] = "controller override policy"
            })
            .Build();

        var router = new ProviderRouter(configuration);

        var standard = router.Resolve(new PlayGateway.ProviderRouteRequest(
            Purpose: "summary",
            Prompt: "hello",
            StructuredOutput: false,
            MaxTokens: 300,
            SessionId: "session-standard"));
        var complex = router.Resolve(new PlayGateway.ProviderRouteRequest(
            Purpose: "analysis",
            Prompt: "hello",
            StructuredOutput: false,
            MaxTokens: 950,
            SessionId: "session-complex"));

        Assert.Equal("gpt-5.5-codex", standard.SelectedModel);
        Assert.Equal("medium", standard.ReasoningEffort);
        Assert.Equal("claude-opus-4.1-thinking", complex.SelectedModel);
        Assert.Equal("controller override policy", complex.Policy);
    }

    [Fact]
    public void Resolve_IgnoresInvalidTierPolicyOverrides()
    {
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["AiGateway:Providers:AiMagicx:Enabled"] = "true",
                ["AiGateway:Routing:ComplexTokenThreshold"] = "-25",
                ["AiGateway:Routing:Standard:SelectedModel"] = "   ",
                ["AiGateway:Routing:Standard:EstimatedCostUsdFloor"] = "-0.2",
                ["AiGateway:Routing:Complex:SelectedModel"] = "",
                ["AiGateway:Routing:Complex:EstimatedCostUsd"] = "-1",
                ["AiGateway:Routing:Complex:Policy"] = "   "
            })
            .Build();

        var router = new ProviderRouter(configuration);

        var standard = router.Resolve(new PlayGateway.ProviderRouteRequest(
            Purpose: "summary",
            Prompt: "hello",
            StructuredOutput: false,
            MaxTokens: 400,
            SessionId: "session-standard"));
        var complex = router.Resolve(new PlayGateway.ProviderRouteRequest(
            Purpose: "analysis",
            Prompt: "hello",
            StructuredOutput: false,
            MaxTokens: 1200,
            SessionId: "session-complex"));

        Assert.Equal("gpt-5.5", standard.SelectedModel);
        Assert.Equal(0.005d, standard.EstimatedCostUsd);
        Assert.Equal("claude-opus-4.1", complex.SelectedModel);
        Assert.Equal(0.0753d, complex.EstimatedCostUsd);
        Assert.Equal("complex keyword policy", complex.Policy);
    }
}
