using Chummer.Run.Contracts.BuildGhost;
using Microsoft.Extensions.Configuration;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Security.Cryptography;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace Chummer.Run.AI.Services.BuildGhost;

public static class BuildGhostPrivateToolDeploymentContract
{
    public const string EndpointConfigurationKey = "CHUMMER_BUILD_GHOST_PRIVATE_TOOL_ENDPOINT";
    public const string AudienceConfigurationKey = "CHUMMER_BUILD_GHOST_PRIVATE_TOOL_AUTH_AUDIENCE";
    public const string RemoteExecutionConfigurationKey = "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_REMOTE_EXECUTION_ENABLED";

    public static BuildGhostPrivateToolDeploymentValidation FromConfiguration(IConfiguration configuration)
    {
        ArgumentNullException.ThrowIfNull(configuration);
        List<string> reasons = [];
        string endpointValue = configuration[EndpointConfigurationKey]?.Trim() ?? string.Empty;
        string audience = configuration[AudienceConfigurationKey]?.Trim() ?? string.Empty;
        bool remoteExecutionEnabled = bool.TryParse(configuration[RemoteExecutionConfigurationKey], out bool enabled) && enabled;
        if (!Uri.TryCreate(endpointValue, UriKind.Absolute, out Uri? endpoint)) reasons.Add("private-tool-endpoint-missing-or-invalid");
        if (!IsSafeAudience(audience)) reasons.Add("private-tool-auth-audience-missing-or-invalid");
        if (remoteExecutionEnabled) reasons.Add("remote-execution-must-remain-disabled");
        if (reasons.Count != 0)
        {
            return new BuildGhostPrivateToolDeploymentValidation(false, null, reasons);
        }

        try
        {
            return new BuildGhostPrivateToolDeploymentValidation(true, Create(endpoint!, audience), []);
        }
        catch (ArgumentException exception)
        {
            return new BuildGhostPrivateToolDeploymentValidation(false, null, [exception.Message]);
        }
    }

    public static BuildGhostPrivateToolDeploymentPackage Create(Uri endpoint, string authenticationAudience)
    {
        RequireChummerToolEndpoint(endpoint);
        if (!IsSafeAudience(authenticationAudience))
        {
            throw new ArgumentException("A non-secret private tool audience is required.", nameof(authenticationAudience));
        }

        JsonObject bodySchema = new()
        {
            ["type"] = "object",
            ["additionalProperties"] = false,
            ["properties"] = new JsonObject
            {
                ["packet_access_key"] = Property("string", "Opaque short-lived Chummer packet key. Copy exactly and never disclose."),
                ["packet_digest"] = Property("string", "Exact sha256 packet digest supplied by Chummer."),
                ["locale"] = new JsonObject
                {
                    ["type"] = "string",
                    ["enum"] = new JsonArray(ToughTongueBuildGhostScenarioContract.CanonicalLocales.Select(static locale => JsonValue.Create(locale)).ToArray())
                },
                ["request_kind"] = new JsonObject
                {
                    ["type"] = "string",
                    ["enum"] = new JsonArray("current-build", "build-tips", "rule-explanation", "build-variants", "group-gaps")
                },
                ["question"] = Property("string", "Current user question without inferred runner or team facts.")
            },
            ["required"] = new JsonArray("packet_access_key", "packet_digest", "locale", "request_kind")
        };
        string bodySchemaJson = CanonicalJson(bodySchema);
        JsonObject toolAuthority = new()
        {
            ["schema"] = ToughTongueBuildGhostContractVersions.PrivateToolContractV1,
            ["name"] = "get_chummer_build_analysis",
            ["httpMethod"] = "POST",
            ["endpoint"] = endpoint.AbsoluteUri,
            ["requiredHeaderNames"] = new JsonArray("Authorization", "X-Chummer-Build-Ghost-Tool-Contract"),
            ["bodySchema"] = JsonNode.Parse(bodySchemaJson),
            ["maximumResponseCharacters"] = 15_000,
            ["timeoutSeconds"] = 120
        };
        string toolDigest = Digest(toolAuthority);
        BuildGhostPrivateToolDefinition tool = new(
            ToughTongueBuildGhostContractVersions.PrivateToolContractV1,
            "get_chummer_build_analysis",
            "Fetch the current digest-bound Chummer Build Ghost analysis. Never infer missing facts or reveal packet keys.",
            "POST",
            endpoint,
            ["Authorization", "X-Chummer-Build-Ghost-Tool-Contract"],
            bodySchemaJson,
            15_000,
            120,
            toolDigest);
        JsonObject packageAuthority = new()
        {
            ["schema"] = ToughTongueBuildGhostContractVersions.PrivateToolDeploymentV1,
            ["deploymentId"] = "build-ghost-private-tool-v1",
            ["toolContractDigest"] = toolDigest,
            ["authenticationScheme"] = "ephemeral-bearer",
            ["authenticationAudience"] = authenticationAudience,
            ["responseSchema"] = ToughTongueBuildGhostContractVersions.AnalysisV1,
            ["packetAccessTtlSeconds"] = 300,
            ["providerNeutral"] = true,
            ["remoteExecutionEnabled"] = false
        };
        return new BuildGhostPrivateToolDeploymentPackage(
            ToughTongueBuildGhostContractVersions.PrivateToolDeploymentV1,
            "build-ghost-private-tool-v1",
            tool,
            "ephemeral-bearer",
            authenticationAudience,
            ToughTongueBuildGhostContractVersions.AnalysisV1,
            300,
            true,
            false,
            Digest(packageAuthority));
    }

    private static void RequireChummerToolEndpoint(Uri endpoint)
    {
        if (!endpoint.IsAbsoluteUri
            || !string.Equals(endpoint.Scheme, Uri.UriSchemeHttps, StringComparison.OrdinalIgnoreCase)
            || (!string.Equals(endpoint.Host, "chummer.run", StringComparison.OrdinalIgnoreCase)
                && !endpoint.Host.EndsWith(".chummer.run", StringComparison.OrdinalIgnoreCase))
            || !string.Equals(endpoint.AbsolutePath, "/api/v1/ai/build-ghost/tool", StringComparison.Ordinal)
            || !string.IsNullOrEmpty(endpoint.UserInfo)
            || !string.IsNullOrEmpty(endpoint.Query)
            || !string.IsNullOrEmpty(endpoint.Fragment))
        {
            throw new ArgumentException("private-tool-endpoint-must-be-exact-chummer-https-route", nameof(endpoint));
        }
    }

    private static bool IsSafeAudience(string value)
        => value.Length is >= 3 and <= 128
            && value.All(static character => char.IsAsciiLetterOrDigit(character) || character is '.' or '-' or '_' or ':' or '/');

    private static JsonObject Property(string type, string description)
        => new() { ["type"] = type, ["description"] = description };

    private static string Digest(JsonNode node)
        => $"sha256:{Convert.ToHexString(SHA256.HashData(JsonSerializer.SerializeToUtf8Bytes(node, new JsonSerializerOptions { WriteIndented = false }))).ToLowerInvariant()}";

    private static string CanonicalJson(JsonNode node)
        => node.ToJsonString(new JsonSerializerOptions { WriteIndented = false });
}

public static class BuildGhostCascadePrivateVoiceBindingContract
{
    public static BuildGhostCascadePrivateVoiceBinding Create(
        string providerVoiceRef,
        string voiceReleaseDigest,
        IReadOnlyList<string> supportedLocales)
    {
        ArgumentNullException.ThrowIfNull(supportedLocales);
        string normalizedRef = providerVoiceRef?.Trim() ?? string.Empty;
        if (!IsOpaqueProviderRef(normalizedRef)) throw new ArgumentException("private-provider-voice-ref-invalid", nameof(providerVoiceRef));
        if (!IsSha256(voiceReleaseDigest)) throw new ArgumentException("voice-release-digest-invalid", nameof(voiceReleaseDigest));
        if (!supportedLocales.SequenceEqual(ToughTongueBuildGhostScenarioContract.CanonicalLocales, StringComparer.Ordinal))
        {
            throw new ArgumentException("voice-binding-locales-must-match-canonical-authority", nameof(supportedLocales));
        }

        JsonObject authority = new()
        {
            ["schema"] = ToughTongueBuildGhostContractVersions.CascadePrivateVoiceBindingV1,
            ["modelProvider"] = "Landmass",
            ["modelId"] = "cascade",
            ["voiceAlias"] = ToughTongueBuildGhostPersonaIds.RookVoice,
            ["providerVoiceRef"] = normalizedRef,
            ["voiceReleaseDigest"] = voiceReleaseDigest,
            ["private"] = true,
            ["syntheticOrigin"] = true,
            ["readVerified"] = true,
            ["supportedLocales"] = new JsonArray(supportedLocales.Select(static locale => JsonValue.Create(locale)).ToArray())
        };
        string digest = $"sha256:{Convert.ToHexString(SHA256.HashData(JsonSerializer.SerializeToUtf8Bytes(authority))).ToLowerInvariant()}";
        return new BuildGhostCascadePrivateVoiceBinding(
            ToughTongueBuildGhostContractVersions.CascadePrivateVoiceBindingV1,
            "Landmass",
            "cascade",
            ToughTongueBuildGhostPersonaIds.RookVoice,
            normalizedRef,
            voiceReleaseDigest,
            true,
            true,
            true,
            supportedLocales.ToArray(),
            digest);
    }

    private static bool IsOpaqueProviderRef(string value)
        => value.Length is >= 8 and <= 128
            && !value.Contains('@', StringComparison.Ordinal)
            && !value.Contains("://", StringComparison.Ordinal)
            && value.All(static character => char.IsAsciiLetterOrDigit(character) || character is '-' or '_' or ':' or '.');

    private static bool IsSha256(string value)
        => value is { Length: 71 }
            && value.StartsWith("sha256:", StringComparison.Ordinal)
            && value.AsSpan(7).ToString().All(static character => character is >= '0' and <= '9' or >= 'a' and <= 'f');
}

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
        BuildGhostPrivateToolDeploymentPackage deployment,
        Uri avatarUrl,
        BuildGhostCascadePrivateVoiceBinding runtimeBinding)
    {
        ArgumentNullException.ThrowIfNull(deployment);
        ArgumentNullException.ThrowIfNull(runtimeBinding);
        if (deployment.Schema != ToughTongueBuildGhostContractVersions.PrivateToolDeploymentV1
            || !deployment.ProviderNeutral
            || deployment.RemoteExecutionEnabled
            || deployment.Tool.Schema != ToughTongueBuildGhostContractVersions.PrivateToolContractV1)
        {
            throw new ArgumentException("Private tool deployment package is not fail-closed and provider-neutral.", nameof(deployment));
        }
        if (runtimeBinding.Schema != ToughTongueBuildGhostContractVersions.CascadePrivateVoiceBindingV1
            || runtimeBinding.ModelProvider != "Landmass"
            || runtimeBinding.ModelId != "cascade"
            || !runtimeBinding.Private
            || !runtimeBinding.SyntheticOrigin
            || !runtimeBinding.ReadVerified
            || !runtimeBinding.SupportedLocales.SequenceEqual(CanonicalLocales, StringComparer.Ordinal))
        {
            throw new ArgumentException("Cascade private voice binding is not accepted.", nameof(runtimeBinding));
        }
        RequirePublicHttps(avatarUrl, nameof(avatarUrl));
        BuildGhostPrivateToolDefinition tool = deployment.Tool;

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
                ["voice"] = runtimeBinding.ProviderVoiceRef,
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
                ["provider"] = runtimeBinding.ModelProvider,
                ["model"] = runtimeBinding.ModelId
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
                ["tool_contract_digest"] = tool.ContractDigest,
                ["tool_deployment_digest"] = deployment.ContractDigest,
                ["runtime_binding_digest"] = runtimeBinding.ContractDigest,
                ["voice_release_digest"] = runtimeBinding.VoiceReleaseDigest,
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
        JsonObject expectedMetadata = Object(expected.Payload, "user_metadata");
        RequireText(metadata, "tool_deployment_digest", Text(expectedMetadata, "tool_deployment_digest"), "tool-deployment-digest-mismatch", reasons);
        RequireText(metadata, "runtime_binding_digest", Text(expectedMetadata, "runtime_binding_digest"), "runtime-binding-digest-mismatch", reasons);
        RequireText(metadata, "voice_release_digest", Text(expectedMetadata, "voice_release_digest"), "voice-release-digest-mismatch", reasons);
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

public sealed class ToughTongueBuildGhostCanaryHarness(
    IToughTongueBuildGhostScenarioClient scenarios,
    IBuildGhostClock clock,
    IConfiguration configuration)
{
    public const string ReadOnlyEnabledKey = "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_CANARY_READ_ONLY_ENABLED";
    public const string AccessGrantEnabledKey = "CHUMMER_BUILD_GHOST_TOUGH_TONGUE_CANARY_ACCESS_GRANT_ENABLED";
    private readonly IToughTongueBuildGhostScenarioClient _scenarios = scenarios ?? throw new ArgumentNullException(nameof(scenarios));
    private readonly IBuildGhostClock _clock = clock ?? throw new ArgumentNullException(nameof(clock));
    private readonly IConfiguration _configuration = configuration ?? throw new ArgumentNullException(nameof(configuration));

    public async Task<ToughTongueBuildGhostCanaryReceipt> RunAsync(
        string scenarioId,
        ToughTongueBuildGhostScenarioCandidate expected,
        string credential,
        CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(expected);
        bool readEnabled = Enabled(ReadOnlyEnabledKey);
        bool accessGrantEnabled = Enabled(AccessGrantEnabledKey);
        bool remoteExecutionEnabled = Enabled(BuildGhostPrivateToolDeploymentContract.RemoteExecutionConfigurationKey);
        List<string> blockers = [];
        bool readAttempted = false;
        bool scenarioAccepted = false;
        bool grantAttempted = false;
        bool grantCreated = false;
        DateTimeOffset? grantExpiresAt = null;

        if (!readEnabled) blockers.Add("scenario-read-canary-disabled");
        if (!IsScenarioId(scenarioId)) blockers.Add("scenario-id-missing-or-invalid");
        if (string.IsNullOrWhiteSpace(credential)) blockers.Add("fresh-governed-credential-required");
        if (accessGrantEnabled && !remoteExecutionEnabled) blockers.Add("access-grant-blocked-while-remote-execution-disabled");

        if (blockers.Count == 0 || (blockers.Count == 1 && blockers[0] == "access-grant-blocked-while-remote-execution-disabled"))
        {
            readAttempted = true;
            try
            {
                ToughTongueBuildGhostScenarioValidation validation = await _scenarios.VerifyPrivateScenarioAsync(
                    scenarioId,
                    expected,
                    credential,
                    cancellationToken).ConfigureAwait(false);
                scenarioAccepted = validation.Accepted;
                blockers.AddRange(validation.RejectionReasons);
            }
            catch (OperationCanceledException)
            {
                throw;
            }
            catch
            {
                blockers.Add("scenario-read-canary-failed");
            }
        }

        if (accessGrantEnabled && remoteExecutionEnabled && scenarioAccepted && blockers.Count == 0)
        {
            grantAttempted = true;
            try
            {
                ToughTongueBuildGhostScenarioAccessGrant grant = await _scenarios.CreateAccessGrantAsync(
                    scenarioId,
                    credential,
                    cancellationToken).ConfigureAwait(false);
                grantCreated = true;
                grantExpiresAt = grant.ExpiresAtUtc;
            }
            catch (OperationCanceledException)
            {
                throw;
            }
            catch
            {
                blockers.Add("access-grant-canary-failed");
            }
        }

        string outcome = grantCreated
            ? "access-grant-pass"
            : scenarioAccepted && !accessGrantEnabled
                ? "read-only-pass"
                : "blocked";
        JsonObject metadata = Object(expected.Payload, "user_metadata");
        return new ToughTongueBuildGhostCanaryReceipt(
            ToughTongueBuildGhostContractVersions.ScenarioCanaryReceiptV1,
            outcome,
            IsScenarioId(scenarioId) ? DigestText(scenarioId) : string.Empty,
            expected.ContractDigest,
            Text(metadata, "tool_deployment_digest"),
            Text(metadata, "runtime_binding_digest"),
            remoteExecutionEnabled,
            readEnabled,
            readAttempted,
            scenarioAccepted,
            accessGrantEnabled,
            grantAttempted,
            grantCreated,
            grantExpiresAt,
            blockers.Distinct(StringComparer.Ordinal).OrderBy(static reason => reason, StringComparer.Ordinal).ToArray(),
            _clock.UtcNow);
    }

    private bool Enabled(string key)
        => bool.TryParse(_configuration[key], out bool enabled) && enabled;

    private static bool IsScenarioId(string value)
        => value is { Length: 24 }
            && value.All(static character => character is >= '0' and <= '9' or >= 'a' and <= 'f');

    private static JsonObject Object(JsonObject parent, string property)
        => parent[property] as JsonObject ?? new JsonObject();

    private static string Text(JsonObject parent, string property)
        => parent[property]?.GetValue<string>()?.Trim() ?? string.Empty;

    private static string DigestText(string value)
        => $"sha256:{Convert.ToHexString(SHA256.HashData(System.Text.Encoding.UTF8.GetBytes(value))).ToLowerInvariant()}";
}
