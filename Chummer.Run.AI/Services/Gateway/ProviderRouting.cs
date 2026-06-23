using System.Text.Json;

namespace Chummer.Run.AI.Services.Gateway;

public interface IProviderAdapter
{
    AiProvider Provider { get; }
    bool Enabled { get; }
    bool PrimaryForStructuredOutput { get; }
    Task<string> GenerateAsync(ProviderRouteRequest request, CancellationToken cancellationToken);
}

public interface IProviderRouter
{
    ProviderRouteDecision Resolve(ProviderRouteRequest request);
}

public sealed class ProviderRouter : IProviderRouter
{
    private readonly IReadOnlyDictionary<AiProvider, bool> _providerEnabled;
    private readonly GatewayRoutingTierPolicy _tierPolicy;

    public ProviderRouter(IConfiguration configuration)
    {
        var section = ResolveProvidersSection(configuration);
        _providerEnabled = new Dictionary<AiProvider, bool>
        {
            [AiProvider.AiMagicx] = IsEnabled(section, AiProvider.AiMagicx),
            [AiProvider.OneMinAi] = IsEnabled(section, AiProvider.OneMinAi),
            [AiProvider.BrowserAct] = IsEnabled(section, AiProvider.BrowserAct),
            [AiProvider.ChatPlayground] = IsEnabled(section, AiProvider.ChatPlayground),
            [AiProvider.PromptingSystems] = IsEnabled(section, AiProvider.PromptingSystems),
            [AiProvider.MarkupGo] = IsEnabled(section, AiProvider.MarkupGo),
            [AiProvider.PeekShot] = IsEnabled(section, AiProvider.PeekShot)
        };
        _tierPolicy = GatewayRoutingTierPolicy.FromConfiguration(configuration);
    }

    public ProviderRouteDecision Resolve(ProviderRouteRequest request)
    {
        if (_providerEnabled.Values.All(enabled => !enabled))
        {
            return BuildDecision(
                request,
                AiProvider.AiMagicx,
                "No provider adapters are enabled in config.",
                fallbackUsed: true);
        }

        if (request.RequiredProvider is { } requiredProvider)
        {
            return BuildDecision(
                request,
                requiredProvider,
                IsEnabled(requiredProvider)
                    ? "Required provider selected for this workflow."
                    : "Required provider is unavailable in the current runtime configuration.",
                fallbackUsed: !IsEnabled(requiredProvider));
        }

        var preferred = ParsePreferred(request.PreferredProvider);
        if (preferred.HasValue && IsEnabled(preferred.Value))
        {
            return BuildDecision(
                request,
                preferred.Value,
                "Preferred provider requested and enabled.",
                fallbackUsed: false);
        }

        if (request.StructuredOutput && IsEnabled(AiProvider.AiMagicx))
        {
            return BuildDecision(
                request,
                AiProvider.AiMagicx,
                "Structured request uses primary AI Magicx adapter.",
                fallbackUsed: false);
        }

        if (IsEnabled(AiProvider.AiMagicx))
        {
            return BuildDecision(
                request,
                AiProvider.AiMagicx,
                "Default primary adapter for tool-rich workflow.",
                fallbackUsed: false);
        }

        if (IsEnabled(AiProvider.OneMinAi))
        {
            return BuildDecision(
                request,
                AiProvider.OneMinAi,
                "AI Magicx disabled; fallback to 1min.AI for lower-cost path.",
                fallbackUsed: true);
        }

        if (IsEnabled(AiProvider.ChatPlayground))
        {
            return BuildDecision(
                request,
                AiProvider.ChatPlayground,
                "Both primary and fallback adapters are disabled; using eval-only adapter.",
                fallbackUsed: true);
        }

        if (IsEnabled(AiProvider.BrowserAct))
        {
            return BuildDecision(
                request,
                AiProvider.BrowserAct,
                "No preferred provider available; browser adapter selected as last-chance path.",
                fallbackUsed: true);
        }

        return BuildDecision(
            request,
            AiProvider.AiMagicx,
            "No configured fallback enabled; routed to primary provider for evaluation only.",
            fallbackUsed: true);
    }

    private ProviderRouteDecision BuildDecision(
        ProviderRouteRequest request,
        AiProvider provider,
        string reason,
        bool fallbackUsed)
    {
        var tier = request.MaxTokens >= _tierPolicy.ComplexTokenThreshold || request.StructuredOutput ? "complex" : "standard";
        var tierPolicy = tier == "complex"
            ? _tierPolicy.Complex
            : _tierPolicy.Standard;
        var estimatedCostUsd = tier == "complex"
            ? tierPolicy.EstimatedCostUsd
            : Math.Round(Math.Max(tierPolicy.EstimatedCostUsdFloor, request.MaxTokens / 100000d), 4);

        return new ProviderRouteDecision(
            Provider: provider,
            Reason: reason,
            FallbackUsed: fallbackUsed,
            Tier: tier,
            SelectedModel: tierPolicy.SelectedModel,
            ReasoningEffort: tierPolicy.ReasoningEffort,
            EstimatedCostUsd: estimatedCostUsd,
            Policy: tierPolicy.Policy);
    }

    private bool IsEnabled(AiProvider provider)
    {
        if (_providerEnabled.TryGetValue(provider, out var enabled))
        {
            return enabled;
        }

        return false;
    }

    private static AiProvider? ParsePreferred(string? preferredProvider)
    {
        if (string.IsNullOrWhiteSpace(preferredProvider))
        {
            return null;
        }

        if (Enum.TryParse<AiProvider>(preferredProvider, true, out var parsed))
        {
            return parsed;
        }

        return preferredProvider.Equals("aimagicx", StringComparison.OrdinalIgnoreCase)
            ? AiProvider.AiMagicx
            : preferredProvider.Equals("1minai", StringComparison.OrdinalIgnoreCase)
                ? AiProvider.OneMinAi
                : null;
    }

    private static IConfigurationSection ResolveProvidersSection(IConfiguration configuration)
    {
        var section = configuration.GetSection("AiGateway:Providers");
        if (section.Exists())
        {
            return section;
        }

        return configuration.GetSection("Providers");
    }

    private static bool IsEnabled(IConfigurationSection section, AiProvider provider)
    {
        var providerKey = provider switch
        {
            AiProvider.AiMagicx => "AiMagicx",
            AiProvider.OneMinAi => "OneMinAi",
            AiProvider.BrowserAct => "BrowserAct",
            AiProvider.ChatPlayground => "ChatPlayground",
            AiProvider.PromptingSystems => "PromptingSystems",
            AiProvider.MarkupGo => "MarkupGo",
            AiProvider.PeekShot => "PeekShot",
            _ => provider.ToString()
        };

        var defaultEnabled = provider switch
        {
            AiProvider.AiMagicx => true,
            AiProvider.OneMinAi => true,
            _ => false
        };

        return section.GetValue<bool?>($"{providerKey}:Enabled") ?? defaultEnabled;
    }
}

internal sealed record GatewayRoutingTierConfig(
    string SelectedModel,
    string ReasoningEffort,
    double EstimatedCostUsd,
    double EstimatedCostUsdFloor,
    string Policy);

internal sealed record GatewayRoutingTierPolicy(
    int ComplexTokenThreshold,
    GatewayRoutingTierConfig Standard,
    GatewayRoutingTierConfig Complex)
{
    public static GatewayRoutingTierPolicy Default { get; } = new(
        ComplexTokenThreshold: 1200,
        Standard: new GatewayRoutingTierConfig(
            SelectedModel: "gpt-5.5",
            ReasoningEffort: "low",
            EstimatedCostUsd: 0.005,
            EstimatedCostUsdFloor: 0.005,
            Policy: "default routing policy"),
        Complex: new GatewayRoutingTierConfig(
            SelectedModel: "claude-opus-4.1",
            ReasoningEffort: "medium",
            EstimatedCostUsd: 0.0753,
            EstimatedCostUsdFloor: 0.0753,
            Policy: "complex keyword policy"));

    public static GatewayRoutingTierPolicy FromConfiguration(IConfiguration configuration)
    {
        IConfigurationSection section = configuration.GetSection("AiGateway:Routing");
        if (!section.Exists())
        {
            section = configuration.GetSection("Routing");
        }

        return new GatewayRoutingTierPolicy(
            ComplexTokenThreshold: SanitizeThreshold(section.GetValue<int?>("ComplexTokenThreshold"), Default.ComplexTokenThreshold),
            Standard: ReadTier(section.GetSection("Standard"), Default.Standard),
            Complex: ReadTier(section.GetSection("Complex"), Default.Complex));
    }

    private static GatewayRoutingTierConfig ReadTier(IConfigurationSection section, GatewayRoutingTierConfig fallback)
        => new(
            SelectedModel: SanitizeText(section["SelectedModel"], fallback.SelectedModel),
            ReasoningEffort: SanitizeText(section["ReasoningEffort"], fallback.ReasoningEffort),
            EstimatedCostUsd: SanitizeNonNegative(section.GetValue<double?>("EstimatedCostUsd"), fallback.EstimatedCostUsd),
            EstimatedCostUsdFloor: SanitizeNonNegative(section.GetValue<double?>("EstimatedCostUsdFloor"), fallback.EstimatedCostUsdFloor),
            Policy: SanitizeText(section["Policy"], fallback.Policy));

    private static int SanitizeThreshold(int? configuredValue, int fallback)
        => configuredValue is > 0 ? configuredValue.Value : fallback;

    private static double SanitizeNonNegative(double? configuredValue, double fallback)
        => configuredValue is >= 0 ? configuredValue.Value : fallback;

    private static string SanitizeText(string? configuredValue, string fallback)
        => string.IsNullOrWhiteSpace(configuredValue)
            ? fallback
            : configuredValue.Trim();
}

public sealed class MockProviderAdapter : IProviderAdapter
{
    private readonly AiProvider _provider;
    private readonly bool _enabled;
    private readonly bool _primaryForStructuredOutput;

    public MockProviderAdapter(AiProvider provider, bool enabled, bool primaryForStructuredOutput)
    {
        _provider = provider;
        _enabled = enabled;
        _primaryForStructuredOutput = primaryForStructuredOutput;
    }

    public AiProvider Provider => _provider;

    public bool Enabled => _enabled;

    public bool PrimaryForStructuredOutput => _primaryForStructuredOutput;

    public Task<string> GenerateAsync(ProviderRouteRequest request, CancellationToken cancellationToken)
    {
        if (!_enabled)
        {
            throw new InvalidOperationException($"{_provider} is disabled in this environment.");
        }

        var payload = new
        {
            provider = _provider.ToString(),
            purpose = request.Purpose,
            structured = request.StructuredOutput,
            temperature = request.Temperature,
            maxTokens = request.MaxTokens,
            promptPreview = request.Prompt.Length <= 120 ? request.Prompt : request.Prompt[..120],
            timestamp = DateTimeOffset.UtcNow,
            signature = $"{_provider}:{request.Purpose}:{request.Prompt.GetHashCode():X8}"
        };

        if (request.StructuredOutput)
        {
            return Task.FromResult(
                JsonSerializer.Serialize(new { success = true, provider = _provider.ToString(), payload = payload, evidence = new[] { "mock-grounding", request.Purpose } }));
        }

        var renderedPrompt = request.Prompt.Replace("\n", " ", StringComparison.Ordinal);
        return Task.FromResult(
            $"[{_provider}] scaffold output for '{request.Purpose}' using signature {payload.signature}. Prompt preview: {renderedPrompt}");
    }
}
