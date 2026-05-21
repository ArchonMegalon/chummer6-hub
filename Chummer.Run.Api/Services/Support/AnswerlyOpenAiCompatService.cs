using System.Text.Json;
using System.Text.Json.Serialization;
using Chummer.Control.Contracts.Support;
using System.Net.Http.Headers;

namespace Chummer.Run.Api.Services.Support;

public sealed class AnswerlyOpenAiCompatService
{
    private const string DefaultModelId = "answerly-support-assistant";
    private const string DefaultRuleGhostModelId = "sr-rulebot";
    private readonly IChummerAssistantAdapter _assistant;
    private readonly RuleGhostService _ruleGhost;
    private readonly AnswerlyRuntimePolicy _policy;
    private readonly IConfiguration _configuration;
    private readonly IHttpClientFactory _httpClientFactory;

    public AnswerlyOpenAiCompatService(
        IChummerAssistantAdapter assistant,
        RuleGhostService ruleGhost,
        AnswerlyRuntimePolicy policy,
        IConfiguration configuration,
        IHttpClientFactory httpClientFactory)
    {
        _assistant = assistant;
        _ruleGhost = ruleGhost;
        _policy = policy;
        _configuration = configuration;
        _httpClientFactory = httpClientFactory;
    }

    public string ModelId => NormalizeOptional(_configuration["ANSWERLY_OPENAI_COMPAT_MODEL_ID"]) ?? DefaultModelId;
    public string RuleGhostModelId => NormalizeOptional(_configuration["ANSWERLY_OPENAI_COMPAT_RULE_GHOST_MODEL_ID"]) ?? DefaultRuleGhostModelId;

    public bool IsReady =>
        _policy.CanUseOpenAiCompat
        && !string.IsNullOrWhiteSpace(ApiToken);

    public string ApiToken => (_configuration["ANSWERLY_OPENAI_COMPAT_API_TOKEN"] ?? string.Empty).Trim();

    public bool PreferEaUpstream => ReadBoolean("ANSWERLY_OPENAI_COMPAT_EA_PRIMARY_ENABLED", true);

    public bool LocalFallbackEnabled => ReadBoolean("ANSWERLY_OPENAI_COMPAT_LOCAL_FALLBACK_ENABLED", true);

    public string? EaUpstreamBaseUrl
        => NormalizeOptional(_configuration["ANSWERLY_OPENAI_COMPAT_EA_UPSTREAM_BASE_URL"])
            ?? NormalizeOptional(_configuration["CODEXLIZ_OLLAMA_HOST"]);

    public IReadOnlyList<string> SupportedModelIds
    {
        get
        {
            string primary = ModelId;
            List<string> models =
            [
                primary,
                $"openrouter/{primary}",
                $"chummer/{primary}",
                RuleGhostModelId,
                $"openrouter/{RuleGhostModelId}",
                $"chummer/{RuleGhostModelId}",
                "rule-ghost-sr",
                "openrouter/rule-ghost-sr",
                "chummer/rule-ghost-sr"
            ];

            string? configuredAliases = NormalizeOptional(_configuration["ANSWERLY_OPENAI_COMPAT_MODEL_ALIASES"]);
            if (configuredAliases is not null)
            {
                foreach (string alias in configuredAliases
                    .Split([',', ';', '\n', '\r'], StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries))
                {
                    if (!models.Contains(alias, StringComparer.Ordinal))
                    {
                        models.Add(alias);
                    }
                }
            }

            return models;
        }
    }

    private IReadOnlySet<string> RuleGhostModelIds
        => new HashSet<string>(StringComparer.Ordinal)
        {
            RuleGhostModelId,
            $"openrouter/{RuleGhostModelId}",
            $"chummer/{RuleGhostModelId}",
            "rule-ghost-sr",
            "openrouter/rule-ghost-sr",
            "chummer/rule-ghost-sr"
        };

    public OpenAiCompatModelListResponse ListModels()
    {
        if (PreferEaUpstream && TryListModelsFromEa(out OpenAiCompatModelListResponse? upstream))
        {
            return upstream!;
        }

        return BuildLocalModelList();
    }

    public OpenAiCompatChatCompletionResponse Complete(OpenAiCompatChatCompletionRequest request)
    {
        ArgumentNullException.ThrowIfNull(request);

        if (request.Stream)
        {
            throw new InvalidDataException("stream=true is not supported by the Answerly compatibility endpoint.");
        }

        if (PreferEaUpstream && TryCompleteWithEa(request, out OpenAiCompatChatCompletionResponse? upstream))
        {
            return upstream!;
        }

        string resolvedModel = ResolveRequestedModel(request.Model);

        string query = ExtractQuery(request.Messages);
        long created = DateTimeOffset.UtcNow.ToUnixTimeSeconds();
        string content;
        if (RuleGhostModelIds.Contains(resolvedModel))
        {
            content = _ruleGhost.Ask(query).Answer;
        }
        else
        {
            int maxCitations = Math.Clamp(request.MaxCitations ?? 3, 1, 5);
            SupportAssistantResponse answer = _assistant.AskSupport(
                reporterUserId: null,
                reporterSubjectId: null,
                new SupportAssistantRequest(Query: query, MaxCitations: maxCitations));
            content = answer.Answer;
        }

        int promptTokens = EstimateTokens(query);
        int completionTokens = EstimateTokens(content);

        return new OpenAiCompatChatCompletionResponse(
            Id: $"chatcmpl_{Guid.NewGuid():N}",
            Object: "chat.completion",
            Created: created,
            Model: resolvedModel,
            Choices:
            [
                new OpenAiCompatChoice(
                    Index: 0,
                    Message: new OpenAiCompatAssistantMessage("assistant", content),
                    FinishReason: "stop")
            ],
            Usage: new OpenAiCompatUsage(
                PromptTokens: promptTokens,
                CompletionTokens: completionTokens,
                TotalTokens: promptTokens + completionTokens));
    }

    private OpenAiCompatModelListResponse BuildLocalModelList()
        => new(
            Object: "list",
            Data: SupportedModelIds
                .Select(id => new OpenAiCompatModelDescriptor(
                    Id: id,
                    Object: "model",
                    Created: DateTimeOffset.UtcNow.ToUnixTimeSeconds(),
                    OwnedBy: "chummer.run"))
                .ToArray());

    private bool TryListModelsFromEa(out OpenAiCompatModelListResponse? response)
    {
        response = null;
        foreach (string url in EnumerateEaUrls("/api/v1/models", "/v1/models"))
        {
            try
            {
                using HttpRequestMessage request = new(HttpMethod.Get, url);
                PrepareEaHeaders(request);
                using HttpResponseMessage http = _httpClientFactory.CreateClient(nameof(AnswerlyOpenAiCompatService))
                    .Send(request);
                if (!http.IsSuccessStatusCode)
                {
                    continue;
                }

                using Stream stream = http.Content.ReadAsStream();
                response = JsonSerializer.Deserialize<OpenAiCompatModelListResponse>(stream);
                if (response is not null)
                {
                    return true;
                }
            }
            catch
            {
            }
        }

        return false;
    }

    private bool TryCompleteWithEa(OpenAiCompatChatCompletionRequest request, out OpenAiCompatChatCompletionResponse? response)
    {
        response = null;
        foreach (string url in EnumerateEaUrls("/api/v1/chat/completions", "/v1/chat/completions"))
        {
            try
            {
                using HttpRequestMessage httpRequest = new(HttpMethod.Post, url)
                {
                    Content = JsonContent.Create(request)
                };
                PrepareEaHeaders(httpRequest);
                using HttpResponseMessage http = _httpClientFactory.CreateClient(nameof(AnswerlyOpenAiCompatService))
                    .Send(httpRequest);
                if (!http.IsSuccessStatusCode)
                {
                    continue;
                }

                using Stream stream = http.Content.ReadAsStream();
                response = JsonSerializer.Deserialize<OpenAiCompatChatCompletionResponse>(stream);
                if (response is not null)
                {
                    return true;
                }
            }
            catch
            {
            }
        }

        return false;
    }

    private IEnumerable<string> EnumerateEaUrls(params string[] candidatePaths)
    {
        string? baseUrl = EaUpstreamBaseUrl;
        if (baseUrl is null)
        {
            yield break;
        }

        string trimmed = baseUrl.TrimEnd('/');
        foreach (string path in candidatePaths)
        {
            yield return $"{trimmed}{path}";
        }
    }

    private void PrepareEaHeaders(HttpRequestMessage request)
    {
        request.Headers.Accept.Add(new MediaTypeWithQualityHeaderValue("application/json"));

        string? upstreamBearer = NormalizeOptional(_configuration["ANSWERLY_OPENAI_COMPAT_EA_UPSTREAM_BEARER_TOKEN"]);
        if (upstreamBearer is not null)
        {
            request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", upstreamBearer);
        }

        AddOptionalHeader(request, "CF-Access-Client-Id",
            NormalizeOptional(_configuration["ANSWERLY_OPENAI_COMPAT_EA_CF_ACCESS_CLIENT_ID"])
            ?? NormalizeOptional(_configuration["CODEXLIZ_CF_ACCESS_CLIENT_ID"]));
        AddOptionalHeader(request, "CF-Access-Client-Secret",
            NormalizeOptional(_configuration["ANSWERLY_OPENAI_COMPAT_EA_CF_ACCESS_CLIENT_SECRET"])
            ?? NormalizeOptional(_configuration["CODEXLIZ_CF_ACCESS_CLIENT_SECRET"]));
        AddOptionalHeader(request, "HTTP-Referer", NormalizeOptional(_configuration["ANSWERLY_OPENAI_COMPAT_EA_HTTP_REFERER"]));
        AddOptionalHeader(request, "X-Title", NormalizeOptional(_configuration["ANSWERLY_OPENAI_COMPAT_EA_X_TITLE"]));
    }

    private static void AddOptionalHeader(HttpRequestMessage request, string name, string? value)
    {
        if (value is not null)
        {
            request.Headers.TryAddWithoutValidation(name, value);
        }
    }

    private string ResolveRequestedModel(string? requestedModel)
    {
        string candidate = requestedModel?.Trim() ?? string.Empty;
        if (string.IsNullOrWhiteSpace(candidate))
        {
            throw new InvalidDataException("model is required.");
        }

        foreach (string supported in SupportedModelIds)
        {
            if (string.Equals(candidate, supported, StringComparison.Ordinal))
            {
                return supported;
            }
        }

        throw new InvalidDataException($"model '{requestedModel}' is not available on this endpoint.");
    }

    private static string ExtractQuery(IReadOnlyList<OpenAiCompatInputMessage>? messages)
    {
        if (messages is null || messages.Count == 0)
        {
            throw new InvalidDataException("messages must contain at least one user message.");
        }

        for (int index = messages.Count - 1; index >= 0; index--)
        {
            OpenAiCompatInputMessage message = messages[index];
            if (!string.Equals(message.Role, "user", StringComparison.OrdinalIgnoreCase))
            {
                continue;
            }

            string content = ExtractMessageContent(message.Content);
            if (!string.IsNullOrWhiteSpace(content))
            {
                return content;
            }
        }

        throw new InvalidDataException("messages must contain a user message with text content.");
    }

    private static string ExtractMessageContent(JsonElement content)
    {
        return content.ValueKind switch
        {
            JsonValueKind.String => content.GetString()?.Trim() ?? string.Empty,
            JsonValueKind.Array => string.Join(
                "\n",
                content.EnumerateArray()
                    .Select(static item =>
                    {
                        if (item.ValueKind != JsonValueKind.Object)
                        {
                            return string.Empty;
                        }

                        if (!item.TryGetProperty("type", out JsonElement type)
                            || !string.Equals(type.GetString(), "text", StringComparison.OrdinalIgnoreCase))
                        {
                            return string.Empty;
                        }

                        return item.TryGetProperty("text", out JsonElement text)
                            ? text.GetString()?.Trim() ?? string.Empty
                            : string.Empty;
                    })
                    .Where(static item => !string.IsNullOrWhiteSpace(item))),
            _ => string.Empty
        };
    }

    private static int EstimateTokens(string content)
    {
        if (string.IsNullOrWhiteSpace(content))
        {
            return 0;
        }

        return content
            .Split([' ', '\r', '\n', '\t'], StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)
            .Length;
    }

    private static string? NormalizeOptional(string? value)
        => string.IsNullOrWhiteSpace(value)
            ? null
            : value.Trim();

    private bool ReadBoolean(string key, bool fallback)
        => bool.TryParse(_configuration[key], out bool parsed) ? parsed : fallback;
}

public sealed record OpenAiCompatChatCompletionRequest(
    [property: JsonPropertyName("model")] string Model,
    [property: JsonPropertyName("messages")] IReadOnlyList<OpenAiCompatInputMessage> Messages,
    [property: JsonPropertyName("stream")] bool Stream = false,
    [property: JsonPropertyName("max_tokens")] int? MaxTokens = null,
    [property: JsonPropertyName("temperature")] decimal? Temperature = null,
    [property: JsonPropertyName("user")] string? User = null,
    [property: JsonPropertyName("max_citations")] int? MaxCitations = null);

public sealed record OpenAiCompatInputMessage(
    [property: JsonPropertyName("role")] string Role,
    [property: JsonPropertyName("content")] JsonElement Content);

public sealed record OpenAiCompatAssistantMessage(
    [property: JsonPropertyName("role")] string Role,
    [property: JsonPropertyName("content")] string Content);

public sealed record OpenAiCompatChoice(
    [property: JsonPropertyName("index")] int Index,
    [property: JsonPropertyName("message")] OpenAiCompatAssistantMessage Message,
    [property: JsonPropertyName("finish_reason")] string FinishReason);

public sealed record OpenAiCompatUsage(
    [property: JsonPropertyName("prompt_tokens")] int PromptTokens,
    [property: JsonPropertyName("completion_tokens")] int CompletionTokens,
    [property: JsonPropertyName("total_tokens")] int TotalTokens);

public sealed record OpenAiCompatChatCompletionResponse(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("object")] string Object,
    [property: JsonPropertyName("created")] long Created,
    [property: JsonPropertyName("model")] string Model,
    [property: JsonPropertyName("choices")] IReadOnlyList<OpenAiCompatChoice> Choices,
    [property: JsonPropertyName("usage")] OpenAiCompatUsage Usage);

public sealed record OpenAiCompatModelDescriptor(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("object")] string Object,
    [property: JsonPropertyName("created")] long Created,
    [property: JsonPropertyName("owned_by")] string OwnedBy);

public sealed record OpenAiCompatModelListResponse(
    [property: JsonPropertyName("object")] string Object,
    [property: JsonPropertyName("data")] IReadOnlyList<OpenAiCompatModelDescriptor> Data);
