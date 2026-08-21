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
        BuildGhostCartesiaPrivateVoiceReadReceipt receipt,
        IReadOnlyList<string> supportedLocales)
    {
        ArgumentNullException.ThrowIfNull(receipt);
        ArgumentNullException.ThrowIfNull(supportedLocales);
        IReadOnlyList<string> receiptFailures = ValidateReceipt(receipt);
        if (receiptFailures.Count != 0)
        {
            throw new ArgumentException(string.Join(',', receiptFailures), nameof(receipt));
        }
        if (!supportedLocales.SequenceEqual(ToughTongueBuildGhostScenarioContract.CanonicalLocales, StringComparer.Ordinal))
        {
            throw new ArgumentException("voice-binding-locales-must-match-canonical-authority", nameof(supportedLocales));
        }

        string receiptDigest = Digest(ReceiptAuthority(receipt));
        BuildGhostCascadePrivateVoiceBinding binding = new(
            ToughTongueBuildGhostContractVersions.CascadePrivateVoiceBindingV1,
            "Landmass",
            "cascade",
            ToughTongueBuildGhostVoiceProviders.CartesiaTtsProvider,
            ToughTongueBuildGhostVoiceProviders.CartesiaNamespace,
            ToughTongueBuildGhostPersonaIds.RookVoice,
            receipt.ReturnedVoiceId,
            receipt.SourceVoiceReleaseDigest,
            receiptDigest,
            supportedLocales.ToArray(),
            string.Empty);
        return binding with { ContractDigest = Digest(BindingAuthority(binding)) };
    }

    public static IReadOnlyList<string> Validate(BuildGhostCascadePrivateVoiceBinding? binding)
    {
        List<string> failures = [];
        if (binding is null) return ["cascade-private-voice-binding-missing"];
        if (binding.Schema != ToughTongueBuildGhostContractVersions.CascadePrivateVoiceBindingV1) failures.Add("voice-binding-schema-invalid");
        if (binding.ModelProvider != "Landmass") failures.Add("voice-binding-model-provider-invalid");
        if (binding.ModelId != "cascade") failures.Add("voice-binding-model-invalid");
        if (binding.TtsProvider != ToughTongueBuildGhostVoiceProviders.CartesiaTtsProvider) failures.Add("voice-binding-tts-provider-invalid");
        if (binding.ProviderNamespace != ToughTongueBuildGhostVoiceProviders.CartesiaNamespace) failures.Add("voice-binding-provider-namespace-invalid");
        if (binding.VoiceAlias != ToughTongueBuildGhostPersonaIds.RookVoice) failures.Add("voice-binding-alias-invalid");
        if (!IsCartesiaVoiceId(binding.ProviderVoiceRef)) failures.Add("voice-binding-cartesia-voice-id-invalid");
        if (!IsSha256(binding.VoiceReleaseDigest)) failures.Add("voice-binding-release-digest-invalid");
        if (!IsSha256(binding.VoiceReadReceiptDigest)) failures.Add("voice-binding-read-receipt-digest-invalid");
        if (binding.SupportedLocales is null
            || !binding.SupportedLocales.SequenceEqual(ToughTongueBuildGhostScenarioContract.CanonicalLocales, StringComparer.Ordinal))
        {
            failures.Add("voice-binding-locales-invalid");
        }
        if (failures.Count == 0 && binding.ContractDigest != Digest(BindingAuthority(binding)))
        {
            failures.Add("voice-binding-contract-digest-invalid");
        }
        return failures;
    }

    private static IReadOnlyList<string> ValidateReceipt(BuildGhostCartesiaPrivateVoiceReadReceipt receipt)
    {
        List<string> failures = [];
        if (receipt.Schema != ToughTongueBuildGhostContractVersions.CartesiaPrivateVoiceReadReceiptV1) failures.Add("cartesia-read-receipt-schema-invalid");
        if (receipt.ProviderNamespace != ToughTongueBuildGhostVoiceProviders.CartesiaNamespace) failures.Add("cartesia-provider-namespace-invalid");
        if (!IsCartesiaVoiceId(receipt.RequestedVoiceId) || !IsCartesiaVoiceId(receipt.ReturnedVoiceId)) failures.Add("cartesia-voice-id-invalid");
        if (!string.Equals(receipt.RequestedVoiceId, receipt.ReturnedVoiceId, StringComparison.Ordinal)) failures.Add("cartesia-voice-id-read-mismatch");
        if (receipt.ReadHttpStatus != 200) failures.Add("cartesia-voice-read-http-status-invalid");
        if (!receipt.IsOwner) failures.Add("cartesia-voice-owner-invalid");
        if (receipt.Access != "private") failures.Add("cartesia-voice-access-not-private");
        if (receipt.Visibility != "owner") failures.Add("cartesia-voice-visibility-not-owner");
        if (receipt.SyntheticProvenance != ToughTongueBuildGhostVoiceProviders.FullySyntheticProvenance) failures.Add("cartesia-voice-synthetic-provenance-invalid");
        if (!IsSha256(receipt.SourceVoiceReleaseDigest)) failures.Add("cartesia-voice-source-release-digest-invalid");
        if (!IsSha256(receipt.ProviderResponseDigest)) failures.Add("cartesia-voice-provider-response-digest-invalid");
        if (receipt.ObservedAtUtc == default) failures.Add("cartesia-voice-observed-at-invalid");
        return failures;
    }

    private static JsonObject ReceiptAuthority(BuildGhostCartesiaPrivateVoiceReadReceipt receipt)
        => new()
        {
            ["schema"] = receipt.Schema,
            ["providerNamespace"] = receipt.ProviderNamespace,
            ["requestedVoiceId"] = receipt.RequestedVoiceId,
            ["returnedVoiceId"] = receipt.ReturnedVoiceId,
            ["readHttpStatus"] = receipt.ReadHttpStatus,
            ["isOwner"] = receipt.IsOwner,
            ["access"] = receipt.Access,
            ["visibility"] = receipt.Visibility,
            ["syntheticProvenance"] = receipt.SyntheticProvenance,
            ["sourceVoiceReleaseDigest"] = receipt.SourceVoiceReleaseDigest,
            ["providerResponseDigest"] = receipt.ProviderResponseDigest,
            ["observedAtUtc"] = receipt.ObservedAtUtc.ToUniversalTime().ToString("O")
        };

    private static JsonObject BindingAuthority(BuildGhostCascadePrivateVoiceBinding binding)
        => new()
        {
            ["schema"] = binding.Schema,
            ["modelProvider"] = binding.ModelProvider,
            ["modelId"] = binding.ModelId,
            ["ttsProvider"] = binding.TtsProvider,
            ["providerNamespace"] = binding.ProviderNamespace,
            ["voiceAlias"] = binding.VoiceAlias,
            ["providerVoiceRef"] = binding.ProviderVoiceRef,
            ["voiceReleaseDigest"] = binding.VoiceReleaseDigest,
            ["voiceReadReceiptDigest"] = binding.VoiceReadReceiptDigest,
            ["supportedLocales"] = new JsonArray(binding.SupportedLocales.Select(static locale => JsonValue.Create(locale)).ToArray())
        };

    private static bool IsCartesiaVoiceId(string? value)
        => Guid.TryParseExact(value, "D", out Guid parsed)
            && string.Equals(parsed.ToString("D"), value, StringComparison.Ordinal);

    private static bool IsSha256(string? value)
        => value is { Length: 71 }
            && value.StartsWith("sha256:", StringComparison.Ordinal)
            && value.AsSpan(7).ToString().All(static character => character is >= '0' and <= '9' or >= 'a' and <= 'f');

    private static string Digest(JsonNode node)
        => $"sha256:{Convert.ToHexString(SHA256.HashData(JsonSerializer.SerializeToUtf8Bytes(node, new JsonSerializerOptions { WriteIndented = false }))).ToLowerInvariant()}";
}

public static class BuildGhostToughTongueCartesiaScenarioSchemaContract
{
    public const string MissingOrUnverifiedBlocker = "cartesia-scenario-bundle-schema-receipt-missing-or-invalid";
    public const string VerifiedDeploymentId = "dpl_DKFDJRMr7tN6xHLYuhLbBaEVDZi8";
    public const string VerifiedScenarioReadBundleUrl = "https://app.toughtongueai.com/_next/static/chunks/10w5gkzd~f23z.js?dpl=dpl_DKFDJRMr7tN6xHLYuhLbBaEVDZi8";
    public const string VerifiedScenarioReadBundleDigest = "sha256:8a3427924a4eae6f5c7d97c10124178272db17d7c6b6b6189c0bdec78e0dfd14";
    public const long VerifiedScenarioReadBundleBytes = 219_531;
    public const string VerifiedScenarioCreateBundleUrl = "https://app.toughtongueai.com/_next/static/chunks/04i2xipv9rrh-.js?dpl=dpl_DKFDJRMr7tN6xHLYuhLbBaEVDZi8";
    public const string VerifiedScenarioCreateBundleDigest = "sha256:01c2f887b5970283734c086bdbf1c3ec1e6af8f6e07a62e229c0f8cd96f5c1eb";
    public const long VerifiedScenarioCreateBundleBytes = 166_081;
    public const string CreateTtsProviderFieldPath = "tts_provider";
    public const string CreateTtsVoiceIdFieldPath = "tts_voice_id";
    public const string ReadTtsProviderFieldPath = "ai_model_config.tts_provider";
    public const string ReadTtsVoiceIdFieldPath = "ai_model_config.tts_voice_id";

    public static IReadOnlyList<string> Validate(BuildGhostToughTongueCartesiaScenarioSchemaReceipt? receipt)
    {
        if (receipt is null) return [MissingOrUnverifiedBlocker];
        List<string> failures = [];
        if (receipt.Schema != ToughTongueBuildGhostContractVersions.CartesiaScenarioSchemaReceiptV1) failures.Add("cartesia-scenario-schema-receipt-version-invalid");
        if (receipt.ProviderNamespace != ToughTongueBuildGhostVoiceProviders.CartesiaNamespace) failures.Add("cartesia-scenario-schema-provider-namespace-invalid");
        if (receipt.TtsProvider != ToughTongueBuildGhostVoiceProviders.CartesiaTtsProvider) failures.Add("cartesia-scenario-schema-provider-value-invalid");
        if (receipt.DeploymentId != VerifiedDeploymentId) failures.Add("cartesia-scenario-schema-deployment-drift");
        if (receipt.ScenarioReadBundleUrl?.AbsoluteUri != VerifiedScenarioReadBundleUrl) failures.Add("cartesia-scenario-read-bundle-url-drift");
        if (receipt.ScenarioReadBundleDigest != VerifiedScenarioReadBundleDigest) failures.Add("cartesia-scenario-read-bundle-digest-drift");
        if (receipt.ScenarioReadBundleBytes != VerifiedScenarioReadBundleBytes) failures.Add("cartesia-scenario-read-bundle-size-drift");
        if (receipt.ScenarioCreateBundleUrl?.AbsoluteUri != VerifiedScenarioCreateBundleUrl) failures.Add("cartesia-scenario-create-bundle-url-drift");
        if (receipt.ScenarioCreateBundleDigest != VerifiedScenarioCreateBundleDigest) failures.Add("cartesia-scenario-create-bundle-digest-drift");
        if (receipt.ScenarioCreateBundleBytes != VerifiedScenarioCreateBundleBytes) failures.Add("cartesia-scenario-create-bundle-size-drift");
        if (receipt.CreateTtsProviderFieldPath != CreateTtsProviderFieldPath) failures.Add("cartesia-scenario-create-provider-field-drift");
        if (receipt.CreateTtsVoiceIdFieldPath != CreateTtsVoiceIdFieldPath) failures.Add("cartesia-scenario-create-voice-field-drift");
        if (receipt.ReadTtsProviderFieldPath != ReadTtsProviderFieldPath) failures.Add("cartesia-scenario-read-provider-field-drift");
        if (receipt.ReadTtsVoiceIdFieldPath != ReadTtsVoiceIdFieldPath) failures.Add("cartesia-scenario-read-voice-field-drift");
        if (receipt.ObservedAtUtc == default) failures.Add("cartesia-scenario-schema-observed-at-invalid");
        return failures;
    }

    public static string DigestReceipt(BuildGhostToughTongueCartesiaScenarioSchemaReceipt receipt)
        => Digest(new JsonObject
        {
            ["schema"] = receipt.Schema,
            ["providerNamespace"] = receipt.ProviderNamespace,
            ["deploymentId"] = receipt.DeploymentId,
            ["scenarioReadBundleUrl"] = receipt.ScenarioReadBundleUrl.AbsoluteUri,
            ["scenarioReadBundleDigest"] = receipt.ScenarioReadBundleDigest,
            ["scenarioReadBundleBytes"] = receipt.ScenarioReadBundleBytes,
            ["scenarioCreateBundleUrl"] = receipt.ScenarioCreateBundleUrl.AbsoluteUri,
            ["scenarioCreateBundleDigest"] = receipt.ScenarioCreateBundleDigest,
            ["scenarioCreateBundleBytes"] = receipt.ScenarioCreateBundleBytes,
            ["createTtsProviderFieldPath"] = receipt.CreateTtsProviderFieldPath,
            ["createTtsVoiceIdFieldPath"] = receipt.CreateTtsVoiceIdFieldPath,
            ["readTtsProviderFieldPath"] = receipt.ReadTtsProviderFieldPath,
            ["readTtsVoiceIdFieldPath"] = receipt.ReadTtsVoiceIdFieldPath,
            ["ttsProvider"] = receipt.TtsProvider,
            ["observedAtUtc"] = receipt.ObservedAtUtc.ToUniversalTime().ToString("O")
        });

    public static string Read(JsonObject payload, string fieldPath)
    {
        if (!IsSafeFieldPath(fieldPath)) return string.Empty;
        JsonNode? current = payload;
        foreach (string segment in Segments(fieldPath))
        {
            current = current is JsonObject currentObject ? currentObject[segment] : null;
        }
        return current is JsonValue leaf && leaf.TryGetValue(out string? text) ? text?.Trim() ?? string.Empty : string.Empty;
    }

    private static string[] Segments(string value) => value.Split('.', StringSplitOptions.None);

    private static bool IsSafeFieldPath(string? value)
    {
        if (string.IsNullOrEmpty(value)) return false;
        string[] segments = Segments(value);
        return segments.Length is >= 1 and <= 4
            && segments.All(static segment => segment.Length is >= 1 and <= 64
                && segment.All(static character => char.IsAsciiLetterOrDigit(character) || character is '_' or '-'));
    }

    private static string Digest(JsonNode node)
        => $"sha256:{Convert.ToHexString(SHA256.HashData(JsonSerializer.SerializeToUtf8Bytes(node, new JsonSerializerOptions { WriteIndented = false }))).ToLowerInvariant()}";
}

public static class BuildGhostToughTongueCustomFunctionSchemaContract
{
    public const string MissingOrUnverifiedBlocker =
        "tough-tongue-custom-function-schema-receipt-missing-or-untrusted";
    public const string ProviderNamespace = "tough-tongue";
    public const string ToolSettingsFieldPath = "tools_config.tools.custom_function.tool_settings";

    public static IReadOnlyList<string> Validate(
        BuildGhostToughTongueCustomFunctionSchemaReceipt? receipt,
        string? trustedReceiptDigest)
    {
        if (receipt is null || !IsSha256(trustedReceiptDigest)) return [MissingOrUnverifiedBlocker];
        List<string> failures = [];
        if (receipt.Schema != ToughTongueBuildGhostContractVersions.CustomFunctionSchemaReceiptV1) failures.Add("custom-function-schema-receipt-version-invalid");
        if (receipt.ProviderNamespace != ProviderNamespace) failures.Add("custom-function-schema-provider-namespace-invalid");
        if (!IsSafeEvidenceUrl(receipt.EvidenceUrl)) failures.Add("custom-function-schema-evidence-url-invalid");
        if (!IsSha256(receipt.EvidenceDigest)) failures.Add("custom-function-schema-evidence-digest-invalid");
        if (receipt.ToolSettingsFieldPath != ToolSettingsFieldPath) failures.Add("custom-function-tool-settings-field-path-invalid");
        string[] properties =
        [
            receipt.NameProperty,
            receipt.DescriptionProperty,
            receipt.EndpointProperty,
            receipt.HttpMethodProperty,
            receipt.HeadersProperty,
            receipt.BodySchemaProperty,
            receipt.MaximumResponseCharactersProperty,
            receipt.TimeoutSecondsProperty,
            receipt.AuthenticationSchemeProperty,
            receipt.AuthenticationAudienceProperty,
            receipt.ContractDigestProperty
        ];
        if (properties.Any(static property => !IsSafeProperty(property))
            || properties.Distinct(StringComparer.Ordinal).Count() != properties.Length)
        {
            failures.Add("custom-function-tool-settings-properties-invalid");
        }
        if (receipt.AuthorizationHeaderName != "Authorization") failures.Add("custom-function-authorization-header-invalid");
        if (receipt.ContractHeaderName != "X-Chummer-Build-Ghost-Tool-Contract") failures.Add("custom-function-contract-header-invalid");
        if (receipt.PacketAccessKeyAuthorizationTemplate != "Bearer {{packet_access_key}}")
        {
            failures.Add("custom-function-packet-key-authorization-template-invalid");
        }
        if (receipt.ObservedAtUtc == default) failures.Add("custom-function-schema-observed-at-invalid");
        if (failures.Count == 0 && DigestReceipt(receipt) != trustedReceiptDigest)
        {
            failures.Add("custom-function-schema-receipt-digest-untrusted");
        }
        return failures;
    }

    public static string DigestReceipt(BuildGhostToughTongueCustomFunctionSchemaReceipt receipt)
        => Digest(new JsonObject
        {
            ["schema"] = receipt.Schema,
            ["providerNamespace"] = receipt.ProviderNamespace,
            ["evidenceUrl"] = receipt.EvidenceUrl.AbsoluteUri,
            ["evidenceDigest"] = receipt.EvidenceDigest,
            ["toolSettingsFieldPath"] = receipt.ToolSettingsFieldPath,
            ["nameProperty"] = receipt.NameProperty,
            ["descriptionProperty"] = receipt.DescriptionProperty,
            ["endpointProperty"] = receipt.EndpointProperty,
            ["httpMethodProperty"] = receipt.HttpMethodProperty,
            ["headersProperty"] = receipt.HeadersProperty,
            ["bodySchemaProperty"] = receipt.BodySchemaProperty,
            ["maximumResponseCharactersProperty"] = receipt.MaximumResponseCharactersProperty,
            ["timeoutSecondsProperty"] = receipt.TimeoutSecondsProperty,
            ["authenticationSchemeProperty"] = receipt.AuthenticationSchemeProperty,
            ["authenticationAudienceProperty"] = receipt.AuthenticationAudienceProperty,
            ["contractDigestProperty"] = receipt.ContractDigestProperty,
            ["authorizationHeaderName"] = receipt.AuthorizationHeaderName,
            ["contractHeaderName"] = receipt.ContractHeaderName,
            ["packetAccessKeyAuthorizationTemplate"] = receipt.PacketAccessKeyAuthorizationTemplate,
            ["observedAtUtc"] = receipt.ObservedAtUtc.ToUniversalTime().ToString("O")
        });

    public static JsonObject CreateToolSettings(
        BuildGhostPrivateToolDeploymentPackage deployment,
        BuildGhostToughTongueCustomFunctionSchemaReceipt receipt)
    {
        ArgumentNullException.ThrowIfNull(deployment);
        ArgumentNullException.ThrowIfNull(receipt);
        BuildGhostPrivateToolDefinition tool = deployment.Tool;
        return new JsonObject
        {
            [receipt.NameProperty] = tool.Name,
            [receipt.DescriptionProperty] = tool.Description,
            [receipt.EndpointProperty] = tool.Endpoint.AbsoluteUri,
            [receipt.HttpMethodProperty] = tool.HttpMethod,
            [receipt.HeadersProperty] = new JsonObject
            {
                [receipt.AuthorizationHeaderName] = receipt.PacketAccessKeyAuthorizationTemplate,
                [receipt.ContractHeaderName] = tool.ContractDigest
            },
            [receipt.BodySchemaProperty] = JsonNode.Parse(tool.BodySchemaJson),
            [receipt.MaximumResponseCharactersProperty] = tool.MaximumResponseCharacters,
            [receipt.TimeoutSecondsProperty] = tool.TimeoutSeconds,
            [receipt.AuthenticationSchemeProperty] = deployment.AuthenticationScheme,
            [receipt.AuthenticationAudienceProperty] = deployment.AuthenticationAudience,
            [receipt.ContractDigestProperty] = tool.ContractDigest
        };
    }

    private static bool IsSafeEvidenceUrl(Uri? value)
        => value is not null
            && value.IsAbsoluteUri
            && string.Equals(value.Scheme, Uri.UriSchemeHttps, StringComparison.OrdinalIgnoreCase)
            && (string.Equals(value.Host, "toughtongueai.com", StringComparison.OrdinalIgnoreCase)
                || value.Host.EndsWith(".toughtongueai.com", StringComparison.OrdinalIgnoreCase))
            && value.IsDefaultPort
            && string.IsNullOrEmpty(value.UserInfo)
            && string.IsNullOrEmpty(value.Fragment);

    private static bool IsSafeProperty(string? value)
        => value is { Length: >= 1 and <= 64 }
            && value.All(static character => char.IsAsciiLetterOrDigit(character) || character is '_' or '-');

    private static bool IsSha256(string? value)
        => value is { Length: 71 }
            && value.StartsWith("sha256:", StringComparison.Ordinal)
            && value.AsSpan(7).ToString().All(static character => character is >= '0' and <= '9' or >= 'a' and <= 'f');

    private static string Digest(JsonNode node)
        => $"sha256:{Convert.ToHexString(SHA256.HashData(JsonSerializer.SerializeToUtf8Bytes(node, new JsonSerializerOptions { WriteIndented = false }))).ToLowerInvariant()}";
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
        BuildGhostCascadePrivateVoiceBinding runtimeBinding,
        BuildGhostToughTongueCartesiaScenarioSchemaReceipt? scenarioSchemaReceipt = null,
        BuildGhostToughTongueCustomFunctionSchemaReceipt? customFunctionSchemaReceipt = null,
        string? trustedCustomFunctionSchemaReceiptDigest = null)
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
        IReadOnlyList<string> bindingFailures = BuildGhostCascadePrivateVoiceBindingContract.Validate(runtimeBinding);
        if (bindingFailures.Count != 0)
        {
            throw new ArgumentException(string.Join(',', bindingFailures), nameof(runtimeBinding));
        }
        RequirePublicHttps(avatarUrl, nameof(avatarUrl));
        BuildGhostPrivateToolDefinition tool = deployment.Tool;
        IReadOnlyList<string> scenarioSchemaFailures =
            BuildGhostToughTongueCartesiaScenarioSchemaContract.Validate(scenarioSchemaReceipt);
        bool providerSchemaReadVerified = scenarioSchemaFailures.Count == 0;
        string? ttsProviderFieldPath = providerSchemaReadVerified
            ? scenarioSchemaReceipt!.ReadTtsProviderFieldPath
            : null;
        string? ttsVoiceIdFieldPath = providerSchemaReadVerified
            ? scenarioSchemaReceipt!.ReadTtsVoiceIdFieldPath
            : null;
        string scenarioSchemaReceiptDigest = providerSchemaReadVerified
            ? BuildGhostToughTongueCartesiaScenarioSchemaContract.DigestReceipt(scenarioSchemaReceipt!)
            : string.Empty;
        IReadOnlyList<string> customFunctionSchemaFailures =
            BuildGhostToughTongueCustomFunctionSchemaContract.Validate(
                customFunctionSchemaReceipt,
                trustedCustomFunctionSchemaReceiptDigest);
        bool customFunctionSchemaReadVerified = customFunctionSchemaFailures.Count == 0;
        string customFunctionSchemaReceiptDigest = customFunctionSchemaReadVerified
            ? BuildGhostToughTongueCustomFunctionSchemaContract.DigestReceipt(customFunctionSchemaReceipt!)
            : string.Empty;

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
                        ["tool_settings"] = customFunctionSchemaReadVerified
                            ? BuildGhostToughTongueCustomFunctionSchemaContract.CreateToolSettings(
                                deployment,
                                customFunctionSchemaReceipt!)
                            : null
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
                ["tool_endpoint"] = tool.Endpoint.AbsoluteUri,
                ["tool_http_method"] = tool.HttpMethod,
                ["tool_authentication_audience"] = deployment.AuthenticationAudience,
                ["custom_function_schema_receipt_digest"] = customFunctionSchemaReceiptDigest,
                ["runtime_binding_digest"] = runtimeBinding.ContractDigest,
                ["voice_release_digest"] = runtimeBinding.VoiceReleaseDigest,
                ["voice_read_receipt_digest"] = runtimeBinding.VoiceReadReceiptDigest,
                ["tts_provider"] = runtimeBinding.TtsProvider,
                ["provider_namespace"] = runtimeBinding.ProviderNamespace,
                ["tts_provider_schema_receipt_digest"] = scenarioSchemaReceiptDigest,
                ["supported_locales"] = string.Join(',', CanonicalLocales),
                ["release_channel"] = "private-nonproduction-candidate"
            }
        };
        if (providerSchemaReadVerified)
        {
            payload[BuildGhostToughTongueCartesiaScenarioSchemaContract.CreateTtsProviderFieldPath] =
                ToughTongueBuildGhostVoiceProviders.CartesiaTtsProvider;
            payload[BuildGhostToughTongueCartesiaScenarioSchemaContract.CreateTtsVoiceIdFieldPath] =
                runtimeBinding.ProviderVoiceRef;
        }
        string contractDigest = Digest(payload);
        payload["user_metadata"]!["scenario_contract_digest"] = contractDigest;
        return new ToughTongueBuildGhostScenarioCandidate(
            ToughTongueBuildGhostContractVersions.ScenarioContractV1,
            payload,
            tool,
            CanonicalLocales,
            ttsProviderFieldPath,
            ttsVoiceIdFieldPath,
            providerSchemaReadVerified,
            customFunctionSchemaReceipt,
            customFunctionSchemaReceiptDigest,
            customFunctionSchemaReadVerified,
            scenarioSchemaFailures.Concat(customFunctionSchemaFailures)
                .Distinct(StringComparer.Ordinal)
                .OrderBy(static reason => reason, StringComparer.Ordinal)
                .ToArray(),
            contractDigest);
    }

    public static ToughTongueBuildGhostScenarioValidation Validate(
        JsonObject? scenario,
        ToughTongueBuildGhostScenarioCandidate expected)
    {
        ArgumentNullException.ThrowIfNull(expected);
        if (!expected.ProviderSchemaReadVerified
            || !expected.CustomFunctionSchemaReadVerified
            || expected.BlockingReasons.Count != 0)
        {
            IReadOnlyList<string> blockers = expected.BlockingReasons.Count == 0
                ? [BuildGhostToughTongueCartesiaScenarioSchemaContract.MissingOrUnverifiedBlocker]
                : expected.BlockingReasons;
            return new ToughTongueBuildGhostScenarioValidation(
                false,
                null,
                blockers.Distinct(StringComparer.Ordinal).OrderBy(static reason => reason, StringComparer.Ordinal).ToArray());
        }
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
        if (expected.TtsProviderFieldPath is null
            || BuildGhostToughTongueCartesiaScenarioSchemaContract.Read(scenario, expected.TtsProviderFieldPath)
                != ToughTongueBuildGhostVoiceProviders.CartesiaTtsProvider)
        {
            reasons.Add("scenario-tts-provider-mismatch");
        }
        if (expected.TtsVoiceIdFieldPath is null
            || BuildGhostToughTongueCartesiaScenarioSchemaContract.Read(scenario, expected.TtsVoiceIdFieldPath)
                != Text(expected.Payload, BuildGhostToughTongueCartesiaScenarioSchemaContract.CreateTtsVoiceIdFieldPath))
        {
            reasons.Add("scenario-tts-voice-id-mismatch");
        }
        RequireBoolean(Object(scenario, "memory"), "is_memory", expected: false, "scenario-memory-must-be-disabled", reasons);
        JsonObject sessionAnalysis = Object(scenario, "session_analysis");
        RequireBoolean(sessionAnalysis, "is_auto_analysis", expected: false, "scenario-auto-analysis-must-be-disabled", reasons);
        RequireBoolean(sessionAnalysis, "is_auto_submit", expected: false, "scenario-auto-submit-must-be-disabled", reasons);
        RequireBoolean(sessionAnalysis, "email_analysis", expected: false, "scenario-email-analysis-must-be-disabled", reasons);
        RequireBoolean(sessionAnalysis, "email_transcript", expected: false, "scenario-email-transcript-must-be-disabled", reasons);
        RequireBoolean(sessionAnalysis, "multimodal_analysis", expected: false, "scenario-multimodal-analysis-must-be-disabled", reasons);
        RequireBoolean(sessionAnalysis, "enable_extraction", expected: false, "scenario-extraction-must-be-disabled", reasons);
        JsonObject customFunction = Object(Object(Object(scenario, "tools_config"), "tools"), "custom_function");
        RequireBoolean(customFunction, "should_register", expected: true, "custom-function-not-registered", reasons);
        RequireBoolean(customFunction, "add_to_system_prompt", expected: true, "custom-function-not-authoritative", reasons);
        if (expected.CustomFunctionSchemaReceipt is null)
        {
            reasons.Add("custom-function-schema-receipt-missing");
        }
        else
        {
            JsonObject actualSettings = Object(customFunction, "tool_settings");
            JsonObject expectedSettings = Object(
                Object(Object(Object(expected.Payload, "tools_config"), "tools"), "custom_function"),
                "tool_settings");
            if (!JsonNode.DeepEquals(actualSettings, expectedSettings))
            {
                reasons.Add("custom-function-tool-settings-mismatch");
            }
        }
        JsonObject metadata = Object(scenario, "user_metadata");
        RequireText(metadata, "chummer_contract", expected.Schema, "scenario-contract-mismatch", reasons);
        RequireText(metadata, "persona_id", ToughTongueBuildGhostPersonaIds.Rook, "scenario-persona-mismatch", reasons);
        RequireText(metadata, "avatar_id", ToughTongueBuildGhostPersonaIds.RookAvatar, "scenario-avatar-id-mismatch", reasons);
        RequireText(metadata, "voice_id", ToughTongueBuildGhostPersonaIds.RookVoice, "scenario-voice-id-mismatch", reasons);
        RequireText(metadata, "tool_contract_digest", expected.Tool.ContractDigest, "tool-contract-digest-mismatch", reasons);
        JsonObject expectedMetadata = Object(expected.Payload, "user_metadata");
        RequireText(metadata, "tool_deployment_digest", Text(expectedMetadata, "tool_deployment_digest"), "tool-deployment-digest-mismatch", reasons);
        RequireText(metadata, "tool_endpoint", expected.Tool.Endpoint.AbsoluteUri, "tool-endpoint-mismatch", reasons);
        RequireText(metadata, "tool_http_method", expected.Tool.HttpMethod, "tool-http-method-mismatch", reasons);
        RequireText(metadata, "tool_authentication_audience", Text(expectedMetadata, "tool_authentication_audience"), "tool-authentication-audience-mismatch", reasons);
        RequireText(metadata, "custom_function_schema_receipt_digest", expected.CustomFunctionSchemaReceiptDigest, "custom-function-schema-receipt-digest-mismatch", reasons);
        RequireText(metadata, "runtime_binding_digest", Text(expectedMetadata, "runtime_binding_digest"), "runtime-binding-digest-mismatch", reasons);
        RequireText(metadata, "voice_release_digest", Text(expectedMetadata, "voice_release_digest"), "voice-release-digest-mismatch", reasons);
        RequireText(metadata, "voice_read_receipt_digest", Text(expectedMetadata, "voice_read_receipt_digest"), "voice-read-receipt-digest-mismatch", reasons);
        RequireText(metadata, "tts_provider", ToughTongueBuildGhostVoiceProviders.CartesiaTtsProvider, "scenario-tts-provider-metadata-mismatch", reasons);
        RequireText(metadata, "provider_namespace", ToughTongueBuildGhostVoiceProviders.CartesiaNamespace, "scenario-provider-namespace-mismatch", reasons);
        RequireText(metadata, "tts_provider_schema_receipt_digest", Text(expectedMetadata, "tts_provider_schema_receipt_digest"), "scenario-tts-provider-schema-receipt-digest-mismatch", reasons);
        RequireText(metadata, "scenario_contract_digest", expected.ContractDigest, "scenario-contract-digest-mismatch", reasons);
        RequireText(metadata, "supported_locales", string.Join(',', CanonicalLocales), "scenario-locales-mismatch", reasons);
        RequireText(metadata, "release_channel", "private-nonproduction-candidate", "scenario-release-channel-invalid", reasons);

        return new ToughTongueBuildGhostScenarioValidation(
            reasons.Count == 0,
            scenarioId,
            reasons.Distinct(StringComparer.Ordinal).OrderBy(static reason => reason, StringComparer.Ordinal).ToArray());
    }

    public static JsonObject SerializeCreatePayload(ToughTongueBuildGhostScenarioCandidate candidate)
    {
        ArgumentNullException.ThrowIfNull(candidate);
        if (!candidate.ProviderSchemaReadVerified
            || !candidate.CustomFunctionSchemaReadVerified
            || candidate.BlockingReasons.Count != 0)
        {
            throw new InvalidDataException("scenario-create-payload-provider-schema-unverified");
        }
        JsonObject customFunction = Object(Object(Object(candidate.Payload, "tools_config"), "tools"), "custom_function");
        JsonObject toolSettings = Object(customFunction, "tool_settings");
        if (toolSettings.Count == 0
            || candidate.ContractDigest != CreatePayloadDigest(candidate.Payload)
            || Text(Object(candidate.Payload, "user_metadata"), "tool_contract_digest") != candidate.Tool.ContractDigest
            || Text(Object(candidate.Payload, "user_metadata"), "tool_endpoint") != candidate.Tool.Endpoint.AbsoluteUri)
        {
            throw new InvalidDataException("scenario-create-payload-custom-function-unbound");
        }
        return (JsonObject)candidate.Payload.DeepClone();
    }

    private static string CreatePayloadDigest(JsonObject payload)
    {
        JsonObject authority = (JsonObject)payload.DeepClone();
        Object(authority, "user_metadata").Remove("scenario_contract_digest");
        return Digest(authority);
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
        ArgumentNullException.ThrowIfNull(expected);
        ToughTongueBuildGhostScenarioValidation? blocked = BlockedCandidate(expected);
        if (blocked is not null) return blocked;
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
        ToughTongueBuildGhostScenarioValidation? blocked = BlockedCandidate(candidate);
        if (blocked is not null) return (blocked, null);
        EnsurePrivateCanaryMutationsEnabled();
        ValidateCredential(credential);
        EnsureProviderBoundary();
        using HttpRequestMessage request = CreateRequest(HttpMethod.Post, "scenarios", credential);
        request.Content = JsonContent.Create(ToughTongueBuildGhostScenarioContract.SerializeCreatePayload(candidate));
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

    public static bool IsOfficialApiBaseAddress(Uri? baseAddress)
    {
        return baseAddress is not null
            && baseAddress.IsAbsoluteUri
            && string.Equals(baseAddress.Scheme, Uri.UriSchemeHttps, StringComparison.OrdinalIgnoreCase)
            && string.Equals(baseAddress.Host, "api.toughtongueai.com", StringComparison.OrdinalIgnoreCase)
            && baseAddress.IsDefaultPort
            && string.Equals(baseAddress.AbsolutePath.TrimEnd('/'), "/api/public", StringComparison.Ordinal)
            && string.IsNullOrEmpty(baseAddress.UserInfo)
            && string.IsNullOrEmpty(baseAddress.Query)
            && string.IsNullOrEmpty(baseAddress.Fragment);
    }

    private void EnsureProviderBoundary()
    {
        if (!IsOfficialApiBaseAddress(_httpClient.BaseAddress))
        {
            throw new InvalidOperationException("Tough Tongue scenario calls require the official HTTPS public API boundary.");
        }
    }

    private static ToughTongueBuildGhostScenarioValidation? BlockedCandidate(
        ToughTongueBuildGhostScenarioCandidate candidate)
    {
        if (candidate.ProviderSchemaReadVerified
            && candidate.CustomFunctionSchemaReadVerified
            && candidate.BlockingReasons.Count == 0) return null;
        IReadOnlyList<string> blockers = candidate.BlockingReasons.Count == 0
            ? [BuildGhostToughTongueCartesiaScenarioSchemaContract.MissingOrUnverifiedBlocker]
            : candidate.BlockingReasons;
        return new ToughTongueBuildGhostScenarioValidation(
            false,
            null,
            blockers.Distinct(StringComparer.Ordinal).OrderBy(static reason => reason, StringComparer.Ordinal).ToArray());
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

        if (!expected.ProviderSchemaReadVerified
            || !expected.CustomFunctionSchemaReadVerified
            || expected.BlockingReasons.Count != 0)
        {
            blockers.AddRange(expected.BlockingReasons.Count == 0
                ? [BuildGhostToughTongueCartesiaScenarioSchemaContract.MissingOrUnverifiedBlocker]
                : expected.BlockingReasons);
        }
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
