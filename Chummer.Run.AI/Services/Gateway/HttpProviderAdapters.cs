using System.Net.Http.Json;
using System.Text.Json;

namespace Chummer.Run.AI.Services.Gateway;

public static class GatewayProviderClientNames
{
    public const string BrowserAct = "gateway-provider-browseract";
    public const string PeekShot = "gateway-provider-peekshot";
    public const string MarkupGo = "gateway-provider-markupgo";
}

public sealed record GatewayBinaryArtifact(
    string ContentType,
    string FileName,
    string Base64Payload);

internal sealed record BrowserActPrompt(string Url);

internal sealed record PeekShotPrompt(string Url);

internal sealed record MarkupGoPrompt(
    string Html,
    string FileName);

public sealed class BrowserActGatewayAdapter : IProviderAdapter
{
    private readonly IHttpClientFactory _httpClientFactory;
    private readonly bool _enabled;

    public BrowserActGatewayAdapter(IHttpClientFactory httpClientFactory, IConfiguration configuration)
    {
        _httpClientFactory = httpClientFactory;
        _enabled = GatewayProviderAdapterParsing.ResolveProviderEnabled(configuration, AiProvider.BrowserAct, defaultEnabled: false);
    }

    public AiProvider Provider => AiProvider.BrowserAct;

    public bool Enabled => _enabled;

    public bool PrimaryForStructuredOutput => false;

    public async Task<string> GenerateAsync(ProviderRouteRequest request, CancellationToken cancellationToken)
    {
        EnsureEnabled();
        var prompt = GatewayProviderAdapterParsing.DeserializePrompt<BrowserActPrompt>(request.Prompt, Provider);
        using var response = await _httpClientFactory.CreateClient(GatewayProviderClientNames.BrowserAct)
            .PostAsJsonAsync("/v1/extract", new { url = prompt.Url }, cancellationToken);
        response.EnsureSuccessStatusCode();
        return await response.Content.ReadAsStringAsync(cancellationToken);
    }

    private void EnsureEnabled()
    {
        if (!_enabled)
        {
            throw new InvalidOperationException($"{Provider} is disabled in this environment.");
        }
    }
}

public sealed class PeekShotGatewayAdapter : IProviderAdapter
{
    private readonly IHttpClientFactory _httpClientFactory;
    private readonly bool _enabled;

    public PeekShotGatewayAdapter(IHttpClientFactory httpClientFactory, IConfiguration configuration)
    {
        _httpClientFactory = httpClientFactory;
        _enabled = GatewayProviderAdapterParsing.ResolveProviderEnabled(configuration, AiProvider.PeekShot, defaultEnabled: false);
    }

    public AiProvider Provider => AiProvider.PeekShot;

    public bool Enabled => _enabled;

    public bool PrimaryForStructuredOutput => false;

    public async Task<string> GenerateAsync(ProviderRouteRequest request, CancellationToken cancellationToken)
    {
        EnsureEnabled();
        var prompt = GatewayProviderAdapterParsing.DeserializePrompt<PeekShotPrompt>(request.Prompt, Provider);
        using var response = await _httpClientFactory.CreateClient(GatewayProviderClientNames.PeekShot)
            .PostAsJsonAsync("/v1/screenshot", new { url = prompt.Url }, cancellationToken);
        response.EnsureSuccessStatusCode();
        return await response.Content.ReadAsStringAsync(cancellationToken);
    }

    private void EnsureEnabled()
    {
        if (!_enabled)
        {
            throw new InvalidOperationException($"{Provider} is disabled in this environment.");
        }
    }
}

public sealed class MarkupGoGatewayAdapter : IProviderAdapter
{
    private readonly IHttpClientFactory _httpClientFactory;
    private readonly bool _enabled;

    public MarkupGoGatewayAdapter(IHttpClientFactory httpClientFactory, IConfiguration configuration)
    {
        _httpClientFactory = httpClientFactory;
        _enabled = GatewayProviderAdapterParsing.ResolveProviderEnabled(configuration, AiProvider.MarkupGo, defaultEnabled: false);
    }

    public AiProvider Provider => AiProvider.MarkupGo;

    public bool Enabled => _enabled;

    public bool PrimaryForStructuredOutput => false;

    public async Task<string> GenerateAsync(ProviderRouteRequest request, CancellationToken cancellationToken)
    {
        EnsureEnabled();
        var prompt = GatewayProviderAdapterParsing.DeserializePrompt<MarkupGoPrompt>(request.Prompt, Provider);
        using var response = await _httpClientFactory.CreateClient(GatewayProviderClientNames.MarkupGo)
            .PostAsJsonAsync("/pdf", new
            {
                htmlSource = new
                {
                    html = prompt.Html
                }
            }, cancellationToken);
        response.EnsureSuccessStatusCode();
        var payload = await response.Content.ReadAsByteArrayAsync(cancellationToken);
        return JsonSerializer.Serialize(new GatewayBinaryArtifact(
            ContentType: "application/pdf",
            FileName: string.IsNullOrWhiteSpace(prompt.FileName) ? "artifact.pdf" : prompt.FileName,
            Base64Payload: Convert.ToBase64String(payload)));
    }

    private void EnsureEnabled()
    {
        if (!_enabled)
        {
            throw new InvalidOperationException($"{Provider} is disabled in this environment.");
        }
    }
}

internal static class GatewayProviderAdapterParsing
{
    public static T DeserializePrompt<T>(string prompt, AiProvider provider)
    {
        try
        {
            var result = JsonSerializer.Deserialize<T>(prompt, new JsonSerializerOptions
            {
                PropertyNameCaseInsensitive = true
            });

            return result ?? throw new InvalidOperationException($"{provider} request payload was empty.");
        }
        catch (JsonException ex)
        {
            throw new InvalidOperationException($"{provider} request payload must be valid JSON.", ex);
        }
    }

    public static bool ResolveProviderEnabled(IConfiguration configuration, AiProvider provider, bool defaultEnabled)
    {
        var section = configuration.GetSection("AiGateway:Providers");
        if (!section.Exists())
        {
            section = configuration.GetSection("Providers");
        }

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

        return section.GetValue<bool?>($"{providerKey}:Enabled") ?? defaultEnabled;
    }
}
