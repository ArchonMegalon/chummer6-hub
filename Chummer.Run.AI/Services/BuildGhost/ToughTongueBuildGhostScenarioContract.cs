using Chummer.Run.Contracts.BuildGhost;
using Microsoft.Extensions.Configuration;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Security.Cryptography;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace Chummer.Run.AI.Services.BuildGhost;

public interface IToughTongueBuildGhostScenarioClient
{
    Task<ToughTongueBuildGhostScenarioValidation> VerifyPrivateScenarioAsync(
        string scenarioId,
        ToughTongueBuildGhostScenarioCandidate expected,
        string credential,
        CancellationToken cancellationToken);

    Task<(ToughTongueBuildGhostScenarioValidation Validation, string? ScenarioId)> CreatePrivateCandidateAsync(
        ToughTongueBuildGhostScenarioCandidate candidate,
        string credential,
        CancellationToken cancellationToken);

    Task<ToughTongueBuildGhostScenarioAccessGrant> CreateAccessGrantAsync(
        string scenarioId,
        string credential,
        CancellationToken cancellationToken);
}

public static class ToughTongueBuildGhostScenarioContract
{
    public static readonly IReadOnlyList<string> CanonicalLocales =
        ["de-DE", "en-US", "fr-FR", "ja-JP", "pt-BR", "zh-CN"];

    public static ToughTongueBuildGhostScenarioCandidate CreatePrivateRookCandidate(
        Uri toolEndpoint,
        Uri avatarUrl,
        string providerVoiceId)
    {
        RequirePublicHttps(toolEndpoint, nameof(toolEndpoint));
        RequirePublicHttps(avatarUrl, nameof(avatarUrl));
        ArgumentException.ThrowIfNullOrWhiteSpace(providerVoiceId);

        JsonObject bodySchema = new()
        {
            ["type"] = "object",
            ["additionalProperties"] = false,
            ["properties"] = new JsonObject
            {
                ["packet_access_key"] = Property(
                    "string",
                    "The opaque, short-lived packet key supplied by the Chummer host. Copy it exactly and never say it aloud."),
                ["packet_digest"] = Property(
                    "string",
                    "The sha256 packet digest supplied by the Chummer host. Copy it exactly."),
                ["locale"] = new JsonObject
                {
                    ["type"] = "string",
                    ["description"] = "The exact Chummer locale for the response.",
                    ["enum"] = new JsonArray(CanonicalLocales.Select(static locale => JsonValue.Create(locale)).ToArray())
                },
                ["request_kind"] = new JsonObject
                {
                    ["type"] = "string",
                    ["description"] = "The grounded Build Ghost view needed for the current user question.",
                    ["enum"] = new JsonArray(
                        "current-build",
                        "build-tips",
                        "rule-explanation",
                        "build-variants",
                        "group-gaps")
                },
                ["question"] = Property(
                    "string",
                    "The user's current question, without adding character or team facts.")
            },
            ["required"] = new JsonArray(
                "packet_access_key",
                "packet_digest",
                "locale",
                "request_kind")
        };
        string bodySchemaJson = CanonicalJson(bodySchema);
        JsonObject toolAuthority = new()
        {
            ["schema"] = ToughTongueBuildGhostContractVersions.ToolContractV1,
            ["name"] = "get_chummer_build_analysis",
            ["httpMethod"] = "POST",
            ["endpoint"] = toolEndpoint.AbsoluteUri,
            ["requiredHeaderNames"] = new JsonArray("Authorization", "X-Chummer-Build-Ghost-Tool-Contract"),
            ["bodySchema"] = JsonNode.Parse(bodySchemaJson),
            ["maximumResponseCharacters"] = 15_000,
            ["timeoutSeconds"] = 120
        };
        string toolDigest = Digest(toolAuthority);
        ToughTongueBuildGhostToolDefinition tool = new(
            ToughTongueBuildGhostContractVersions.ToolContractV1,
            "get_chummer_build_analysis",
            "Fetch the current digest-bound Chummer Build Ghost analysis. Call before every build tip, rules answer, variant comparison, optimization explanation, or group-gap answer. Never infer missing facts and never reveal packet keys.",
            "POST",
            toolEndpoint,
            ["Authorization", "X-Chummer-Build-Ghost-Tool-Contract"],
            bodySchemaJson,
            15_000,
            120,
            toolDigest);

        JsonObject payload = new()
        {
            ["name"] = "Rook · Chummer Build Ghost (private candidate)",
            ["description"] = "Private nonproduction Chummer Build Ghost candidate. The Chummer packet is the sole factual authority.",
            ["user_friendly_description"] = "Ask Rook for grounded build tips, rule explanations, and trade-off comparisons.",
            ["ai_instructions"] = Instructions(),
            ["rubrik"] = "Fail the session if Rook invents a character, teammate, rule, source, action, or optimization fact; reveals a packet key; changes language without host authority; or offers an unbound mutation.",
            ["is_public"] = false,
            ["is_recording"] = false,
            ["analysis_access"] = "never",
            ["appearance"] = new JsonObject
            {
                ["voice"] = providerVoiceId.Trim(),
                ["avatar_url"] = avatarUrl.AbsoluteUri,
                ["language_code"] = "en-US"
            },
            ["memory"] = new JsonObject { ["is_memory"] = false },
            ["session_analysis"] = new JsonObject
            {
                ["is_auto_analysis"] = false,
                ["is_auto_submit"] = false,
                ["email_analysis"] = false,
                ["email_transcript"] = false,
                ["multimodal_analysis"] = false,
                ["enable_extraction"] = false
            },
            ["ai_model_config"] = new JsonObject
            {
                ["provider"] = "Landmass",
                ["model"] = "cascade"
            },
            ["tools_config"] = new JsonObject
            {
                ["tools"] = new JsonObject
                {
                    ["custom_function"] = new JsonObject
                    {
                        ["should_register"] = true,
                        ["add_to_system_prompt"] = true,
                        ["tool_settings"] = null
                    },
                    ["end_session"] = new JsonObject
                    {
                        ["should_register"] = true,
                        ["add_to_system_prompt"] = true,
                        ["tool_settings"] = new JsonObject { ["disconnectDelaySeconds"] = 3 }
                    }
                }
            },
            ["user_metadata"] = new JsonObject
            {
                ["chummer_contract"] = ToughTongueBuildGhostContractVersions.ScenarioContractV1,
                ["persona_id"] = ToughTongueBuildGhostPersonaIds.Rook,
                ["avatar_id"] = ToughTongueBuildGhostPersonaIds.RookAvatar,
                ["voice_id"] = ToughTongueBuildGhostPersonaIds.RookVoice,
                ["tool_contract_digest"] = toolDigest,
                ["supported_locales"] = string.Join(',', CanonicalLocales),
                ["release_channel"] = "private-nonproduction-candidate"
            }
        };
        string contractDigest = Digest(payload);
        payload["user_metadata"]!["scenario_contract_digest"] = contractDigest;
        return new ToughTongueBuildGhostScenarioCandidate(
            ToughTongueBuildGhostContractVersions.ScenarioContractV1,
            payload,
            tool,
            CanonicalLocales,
            contractDigest);
    }

    public static ToughTongueBuildGhostScenarioValidation Validate(
        JsonObject? scenario,
        ToughTongueBuildGhostScenarioCandidate expected)
    {
        ArgumentNullException.ThrowIfNull(expected);
        List<string> reasons = [];
        if (scenario is null)
        {
            return new ToughTongueBuildGhostScenarioValidation(false, null, ["scenario-missing"]);
        }

        string? scenarioId = Text(scenario, "id");
        if (!IsObjectId(scenarioId)) reasons.Add("scenario-id-invalid");
        RequireBoolean(scenario, "is_public", expected: false, "scenario-must-be-private", reasons);
        RequireBoolean(scenario, "is_recording", expected: false, "scenario-recording-must-be-disabled", reasons);
        RequireText(scenario, "analysis_access", "never", "scenario-analysis-access-invalid", reasons);
        RequireText(Object(scenario, "appearance"), "voice", Text(Object(expected.Payload, "appearance"), "voice"), "scenario-voice-mismatch", reasons);
        RequireText(Object(scenario, "appearance"), "avatar_url", Text(Object(expected.Payload, "appearance"), "avatar_url"), "scenario-avatar-mismatch", reasons);
        RequireText(Object(scenario, "appearance"), "language_code", "en-US", "scenario-base-locale-invalid", reasons);
        RequireText(Object(scenario, "ai_model_config"), "provider", "Landmass", "scenario-model-provider-invalid", reasons);
        RequireText(Object(scenario, "ai_model_config"), "model", "cascade", "scenario-model-invalid", reasons);
        RequireBoolean(Object(scenario, "memory"), "is_memory", expected: false, "scenario-memory-must-be-disabled", reasons);
        JsonObject customFunction = Object(Object(Object(scenario, "tools_config"), "tools"), "custom_function");
        RequireBoolean(customFunction, "should_register", expected: true, "custom-function-not-registered", reasons);
        RequireBoolean(customFunction, "add_to_system_prompt", expected: true, "custom-function-not-authoritative", reasons);
        JsonObject metadata = Object(scenario, "user_metadata");
        RequireText(metadata, "chummer_contract", expected.Schema, "scenario-contract-mismatch", reasons);
        RequireText(metadata, "persona_id", ToughTongueBuildGhostPersonaIds.Rook, "scenario-persona-mismatch", reasons);
        RequireText(metadata, "avatar_id", ToughTongueBuildGhostPersonaIds.RookAvatar, "scenario-avatar-id-mismatch", reasons);
        RequireText(metadata, "voice_id", ToughTongueBuildGhostPersonaIds.RookVoice, "scenario-voice-id-mismatch", reasons);
        RequireText(metadata, "tool_contract_digest", expected.Tool.ContractDigest, "tool-contract-digest-mismatch", reasons);
        RequireText(metadata, "scenario_contract_digest", expected.ContractDigest, "scenario-contract-digest-mismatch", reasons);
        RequireText(metadata, "supported_locales", string.Join(',', CanonicalLocales), "scenario-locales-mismatch", reasons);
        RequireText(metadata, "release_channel", "private-nonproduction-candidate", "scenario-release-channel-invalid", reasons);

        return new ToughTongueBuildGhostScenarioValidation(
            reasons.Count == 0,
            scenarioId,
            reasons.Distinct(StringComparer.Ordinal).OrderBy(static reason => reason, StringComparer.Ordinal).ToArray());
    }

    private static string Instructions()
        => """
           You are Rook, an adult female ork decker and Chummer Build Ghost. Be concise, practical, dryly warm, and never imitate a real person.
           The Chummer host supplies {{ packet_access_key }}, {{ packet_digest }}, and {{ locale }}. Treat them as opaque secrets: copy them only into get_chummer_build_analysis and never speak, display, transform, log, or guess them.
           Before every build tip, optimization explanation (including drugs), rules answer, alternative build comparison, or group-gap answer, call get_chummer_build_analysis. The tool response is the sole factual authority.
           Use only facts, rule anchors, variants, actions, and visible group conclusions returned by the tool. Never infer hidden teammate details. Never claim an action was applied; Chummer only permits digest- and revision-bound previews after explicit review.
           Answer in exactly {{ locale }}. If the tool rejects the locale, packet key, digest, or request, read its safe fallback in that locale and stop. Do not silently change models, voices, languages, or sources.
           Explain the immediate benefit, long-term ceiling, opportunity cost, dependencies, GM constraints, and risk of each recommendation. Distinguish common optimization patterns from legal/applicable choices for this exact build.
           """;

    private static JsonObject Property(string type, string description)
        => new() { ["type"] = type, ["description"] = description };

    private static void RequirePublicHttps(Uri uri, string parameterName)
    {
        if (!uri.IsAbsoluteUri
            || !string.Equals(uri.Scheme, Uri.UriSchemeHttps, StringComparison.OrdinalIgnoreCase)
            || !string.IsNullOrEmpty(uri.UserInfo)
            || !string.IsNullOrEmpty(uri.Fragment))
        {
            throw new ArgumentException("A public absolute HTTPS URI without credentials or fragment is required.", parameterName);
        }
    }

    private static bool IsObjectId(string? value)
        => value is { Length: 24 }
            && value.All(static character => character is >= '0' and <= '9' or >= 'a' and <= 'f');

    private static JsonObject Object(JsonObject parent, string property)
        => parent[property] as JsonObject ?? new JsonObject();

    private static string Text(JsonObject parent, string property)
        => parent[property]?.GetValue<string>()?.Trim() ?? string.Empty;

    private static void RequireText(
        JsonObject parent,
        string property,
        string expected,
        string failure,
        ICollection<string> reasons)
    {
        if (!string.Equals(Text(parent, property), expected, StringComparison.Ordinal)) reasons.Add(failure);
    }

    private static void RequireBoolean(
        JsonObject parent,
        string property,
        bool expected,
        string failure,
        ICollection<string> reasons)
    {
        if (parent[property] is not JsonValue value
            || !value.TryGetValue(out bool actual)
            || actual != expected)
        {
            reasons.Add(failure);
        }
    }

    private static string Digest(JsonNode node)
        => $"sha256:{Convert.ToHexString(SHA256.HashData(JsonSerializer.SerializeToUtf8Bytes(node, new JsonSerializerOptions { WriteIndented = false }))).ToLowerInvariant()}";

    private static string CanonicalJson(JsonNode node)
        => node.ToJsonString(new JsonSerializerOptions { WriteIndented = false });
}

public sealed class ToughTongueBuildGhostScenarioClient(
    HttpClient httpClient,
    IBuildGhostClock clock,
    IConfiguration configuration) : IToughTongueBuildGhostScenarioClient
{
    private const string PrivateCanaryMutationsEnabledKey =
        "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_PRIVATE_CANARY_MUTATIONS_ENABLED";
    private readonly HttpClient _httpClient = httpClient ?? throw new ArgumentNullException(nameof(httpClient));
    private readonly IBuildGhostClock _clock = clock ?? throw new ArgumentNullException(nameof(clock));
    private readonly bool _privateCanaryMutationsEnabled = bool.TryParse(
        (configuration ?? throw new ArgumentNullException(nameof(configuration)))[PrivateCanaryMutationsEnabledKey],
        out bool enabled) && enabled;

    public async Task<ToughTongueBuildGhostScenarioValidation> VerifyPrivateScenarioAsync(
        string scenarioId,
        ToughTongueBuildGhostScenarioCandidate expected,
        string credential,
        CancellationToken cancellationToken)
    {
        ValidateBoundary(scenarioId, credential);
        using HttpRequestMessage request = CreateRequest(HttpMethod.Get, $"scenarios/{scenarioId}", credential);
        using HttpResponseMessage response = await _httpClient.SendAsync(request, cancellationToken).ConfigureAwait(false);
        if (!response.IsSuccessStatusCode)
        {
            return new ToughTongueBuildGhostScenarioValidation(
                false,
                scenarioId,
                [$"scenario-read-http-{(int)response.StatusCode}"]);
        }

        JsonObject? scenario = await response.Content.ReadFromJsonAsync<JsonObject>(cancellationToken).ConfigureAwait(false);
        return ToughTongueBuildGhostScenarioContract.Validate(scenario, expected);
    }

    public async Task<(ToughTongueBuildGhostScenarioValidation Validation, string? ScenarioId)> CreatePrivateCandidateAsync(
        ToughTongueBuildGhostScenarioCandidate candidate,
        string credential,
        CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(candidate);
        EnsurePrivateCanaryMutationsEnabled();
        ValidateCredential(credential);
        EnsureProviderBoundary();
        using HttpRequestMessage request = CreateRequest(HttpMethod.Post, "scenarios", credential);
        request.Content = JsonContent.Create(candidate.Payload);
        using HttpResponseMessage response = await _httpClient.SendAsync(request, cancellationToken).ConfigureAwait(false);
        if (!response.IsSuccessStatusCode)
        {
            return (new ToughTongueBuildGhostScenarioValidation(
                false,
                null,
                [$"scenario-create-http-{(int)response.StatusCode}"]), null);
        }

        JsonObject? scenario = await response.Content.ReadFromJsonAsync<JsonObject>(cancellationToken).ConfigureAwait(false);
        ToughTongueBuildGhostScenarioValidation validation = ToughTongueBuildGhostScenarioContract.Validate(scenario, candidate);
        return (validation, validation.ScenarioId);
    }

    public async Task<ToughTongueBuildGhostScenarioAccessGrant> CreateAccessGrantAsync(
        string scenarioId,
        string credential,
        CancellationToken cancellationToken)
    {
        EnsurePrivateCanaryMutationsEnabled();
        ValidateBoundary(scenarioId, credential);
        using HttpRequestMessage request = CreateRequest(HttpMethod.Post, "scenario-access-token", credential);
        request.Content = JsonContent.Create(new JsonObject { ["scenario_id"] = scenarioId });
        using HttpResponseMessage response = await _httpClient.SendAsync(request, cancellationToken).ConfigureAwait(false);
        response.EnsureSuccessStatusCode();
        JsonObject payload = await response.Content.ReadFromJsonAsync<JsonObject>(cancellationToken).ConfigureAwait(false)
            ?? throw new InvalidDataException("Tough Tongue access-token response was empty.");
        string accessToken = payload["access_token"]?.GetValue<string>()?.Trim() ?? string.Empty;
        if (accessToken.Length < 32
            || !DateTimeOffset.TryParse(payload["expires_at"]?.GetValue<string>(), out DateTimeOffset expiresAt)
            || expiresAt <= _clock.UtcNow
            || expiresAt > _clock.UtcNow.AddMinutes(65))
        {
            throw new InvalidDataException("Tough Tongue returned an invalid private scenario access grant.");
        }

        return new ToughTongueBuildGhostScenarioAccessGrant(scenarioId, accessToken, expiresAt);
    }

    private void EnsurePrivateCanaryMutationsEnabled()
    {
        if (!_privateCanaryMutationsEnabled)
        {
            throw new InvalidOperationException(
                "Private Tough Tongue candidate mutations are disabled by default.");
        }
    }

    private static void ValidateCredential(string credential)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(credential);
        if (credential.IndexOfAny(['\r', '\n']) >= 0)
        {
            throw new ArgumentException("Credential contains invalid header characters.", nameof(credential));
        }
    }

    private void ValidateBoundary(string scenarioId, string credential)
    {
        ValidateCredential(credential);
        EnsureProviderBoundary();
        if (scenarioId.Length != 24
            || scenarioId.Any(static character => character is not (>= '0' and <= '9' or >= 'a' and <= 'f')))
        {
            throw new ArgumentException("Scenario id must be a lowercase provider object id.", nameof(scenarioId));
        }
    }

    private void EnsureProviderBoundary()
    {
        Uri? baseAddress = _httpClient.BaseAddress;
        if (baseAddress is null
            || !string.Equals(baseAddress.Scheme, Uri.UriSchemeHttps, StringComparison.OrdinalIgnoreCase)
            || !string.Equals(baseAddress.Host, "app.toughtongueai.com", StringComparison.OrdinalIgnoreCase)
            || !baseAddress.AbsolutePath.TrimEnd('/').EndsWith("/api/public", StringComparison.Ordinal))
        {
            throw new InvalidOperationException("Tough Tongue scenario calls require the official HTTPS public API boundary.");
        }
    }

    private static HttpRequestMessage CreateRequest(HttpMethod method, string relativePath, string credential)
    {
        HttpRequestMessage request = new(method, relativePath);
        request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", credential.Trim());
        request.Headers.TryAddWithoutValidation("Accept", "application/json");
        return request;
    }
}
