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

public static class BuildGhostToughTonguePremiumLiveAvatarSchemaContract
{
    public const string MissingOrUnverifiedBlocker =
        "tough-tongue-premium-live-avatar-schema-receipt-missing-or-invalid";
    public const string ProviderNamespace = "tough-tongue";
    public const string VerifiedDeploymentId = "dpl_2hoTJxqMKHBPTX9eyHoXX7cZ1o9i";
    public const string VerifiedStudioBundleUrl =
        "https://app.toughtongueai.com/_next/static/chunks/0dic_u.sbe1xm.js?dpl=dpl_2hoTJxqMKHBPTX9eyHoXX7cZ1o9i";
    public const string VerifiedStudioBundleDigest =
        "sha256:7e22f357c2ebe5e9f6988f6fa4cfec1c332ebf3c0f573e5dc31feaeefcf5c7e7";
    public const long VerifiedStudioBundleBytes = 499_677;
    public const string VerifiedScenarioRuntimeBundleUrl =
        "https://app.toughtongueai.com/_next/static/chunks/0m4xondr3o4oe.js?dpl=dpl_2hoTJxqMKHBPTX9eyHoXX7cZ1o9i";
    public const string VerifiedScenarioRuntimeBundleDigest =
        "sha256:7ba4d63277d18d2ff8c2ffd3128576a1ad15e4670e4f4c9921b6846de6ba71d7";
    public const long VerifiedScenarioRuntimeBundleBytes = 219_531;
    public const string VerifiedSessionCreateBundleUrl =
        "https://app.toughtongueai.com/_next/static/chunks/04i2xipv9rrh-.js?dpl=dpl_2hoTJxqMKHBPTX9eyHoXX7cZ1o9i";
    public const string VerifiedSessionCreateBundleDigest =
        "sha256:01c2f887b5970283734c086bdbf1c3ec1e6af8f6e07a62e229c0f8cd96f5c1eb";
    public const long VerifiedSessionCreateBundleBytes = 166_081;
    public const string ScenarioLiveAvatarIdFieldPath = "appearance.live_avatar_id";
    public const string ScenarioLiveAvatarProviderFieldPath = "appearance.live_avatar_provider";
    public const string RuntimeEnabledFieldPath = "avatar_config.enabled";
    public const string RuntimeAvatarIdFieldPath = "avatar_config.avatar_id";
    public const string RuntimeProviderFieldPath = "avatar_config.provider";

    public static readonly IReadOnlyList<string> AllowedProviders =
    [
        ToughTongueBuildGhostLiveAvatarProviders.Anam,
        ToughTongueBuildGhostLiveAvatarProviders.HeyGen
    ];

    public static IReadOnlyList<string> Validate(
        BuildGhostToughTonguePremiumLiveAvatarSchemaReceipt? receipt)
    {
        if (receipt is null) return [MissingOrUnverifiedBlocker];
        List<string> failures = [];
        if (receipt.Schema != ToughTongueBuildGhostContractVersions.PremiumLiveAvatarSchemaReceiptV1) failures.Add("premium-live-avatar-schema-version-invalid");
        if (receipt.ProviderNamespace != ProviderNamespace) failures.Add("premium-live-avatar-provider-namespace-invalid");
        if (receipt.DeploymentId != VerifiedDeploymentId) failures.Add("premium-live-avatar-deployment-drift");
        RequireBundle(receipt.StudioBundleUrl, receipt.StudioBundleDigest, receipt.StudioBundleBytes,
            VerifiedStudioBundleUrl, VerifiedStudioBundleDigest, VerifiedStudioBundleBytes, "studio", failures);
        RequireBundle(receipt.ScenarioRuntimeBundleUrl, receipt.ScenarioRuntimeBundleDigest, receipt.ScenarioRuntimeBundleBytes,
            VerifiedScenarioRuntimeBundleUrl, VerifiedScenarioRuntimeBundleDigest, VerifiedScenarioRuntimeBundleBytes, "scenario-runtime", failures);
        RequireBundle(receipt.SessionCreateBundleUrl, receipt.SessionCreateBundleDigest, receipt.SessionCreateBundleBytes,
            VerifiedSessionCreateBundleUrl, VerifiedSessionCreateBundleDigest, VerifiedSessionCreateBundleBytes, "session-create", failures);
        if (receipt.ScenarioLiveAvatarIdFieldPath != ScenarioLiveAvatarIdFieldPath) failures.Add("premium-live-avatar-id-field-drift");
        if (receipt.ScenarioLiveAvatarProviderFieldPath != ScenarioLiveAvatarProviderFieldPath) failures.Add("premium-live-avatar-provider-field-drift");
        if (receipt.RuntimeEnabledFieldPath != RuntimeEnabledFieldPath) failures.Add("premium-live-avatar-runtime-enabled-field-drift");
        if (receipt.RuntimeAvatarIdFieldPath != RuntimeAvatarIdFieldPath) failures.Add("premium-live-avatar-runtime-id-field-drift");
        if (receipt.RuntimeProviderFieldPath != RuntimeProviderFieldPath) failures.Add("premium-live-avatar-runtime-provider-field-drift");
        if (receipt.RequiredModelProvider != ToughTongueBuildGhostLiveAvatarProviders.RequiredModelProvider) failures.Add("premium-live-avatar-model-provider-drift");
        if (receipt.AllowedProviders is null
            || !receipt.AllowedProviders.SequenceEqual(AllowedProviders, StringComparer.Ordinal))
        {
            failures.Add("premium-live-avatar-provider-set-drift");
        }
        if (receipt.AnamMinutesMultiplier != ToughTongueBuildGhostLiveAvatarProviders.PremiumMinutesMultiplier) failures.Add("premium-live-avatar-anam-cost-drift");
        if (receipt.HeyGenMinutesMultiplier != ToughTongueBuildGhostLiveAvatarProviders.PremiumMinutesMultiplier) failures.Add("premium-live-avatar-heygen-cost-drift");
        if (!receipt.ProviderManagedLipSynchronizationAdvertised) failures.Add("premium-live-avatar-provider-animation-unverified");
        if (receipt.ObservedAtUtc == default) failures.Add("premium-live-avatar-observed-at-invalid");
        return Ordered(failures);
    }

    public static BuildGhostToughTonguePremiumLiveAvatarBinding CreateBinding(
        BuildGhostToughTonguePremiumLiveAvatarSchemaReceipt receipt,
        string provider,
        string providerAvatarId)
    {
        IReadOnlyList<string> receiptFailures = Validate(receipt);
        if (receiptFailures.Count != 0)
        {
            throw new ArgumentException(string.Join(',', receiptFailures), nameof(receipt));
        }
        if (!AllowedProviders.Contains(provider, StringComparer.Ordinal))
        {
            throw new ArgumentException("premium-live-avatar-provider-not-approved", nameof(provider));
        }
        if (!IsSafeProviderAvatarId(providerAvatarId))
        {
            throw new ArgumentException("premium-live-avatar-id-invalid", nameof(providerAvatarId));
        }

        string schemaReceiptDigest = DigestReceipt(receipt);
        string avatarIdDigest = DigestText(providerAvatarId);
        BuildGhostToughTonguePremiumLiveAvatarBinding binding = new(
            ToughTongueBuildGhostContractVersions.PremiumLiveAvatarBindingV1,
            provider,
            providerAvatarId,
            avatarIdDigest,
            ToughTongueBuildGhostLiveAvatarProviders.RequiredModelProvider,
            ToughTongueBuildGhostLiveAvatarProviders.PremiumMinutesMultiplier,
            ProviderManagedLipSynchronization: true,
            schemaReceiptDigest,
            string.Empty);
        return binding with { ContractDigest = Digest(BindingAuthority(binding)) };
    }

    public static IReadOnlyList<string> ValidateBinding(
        BuildGhostToughTonguePremiumLiveAvatarBinding? binding,
        BuildGhostToughTonguePremiumLiveAvatarSchemaReceipt? receipt)
    {
        List<string> failures = [.. Validate(receipt)];
        if (binding is null)
        {
            failures.Add("premium-live-avatar-binding-missing");
            return Ordered(failures);
        }
        if (binding.Schema != ToughTongueBuildGhostContractVersions.PremiumLiveAvatarBindingV1) failures.Add("premium-live-avatar-binding-version-invalid");
        if (!AllowedProviders.Contains(binding.Provider, StringComparer.Ordinal)) failures.Add("premium-live-avatar-binding-provider-invalid");
        if (!IsSafeProviderAvatarId(binding.ProviderAvatarId)
            || binding.ProviderAvatarIdDigest != DigestText(binding.ProviderAvatarId)) failures.Add("premium-live-avatar-binding-id-invalid");
        if (binding.RequiredModelProvider != ToughTongueBuildGhostLiveAvatarProviders.RequiredModelProvider) failures.Add("premium-live-avatar-binding-model-provider-invalid");
        if (binding.MinutesMultiplier != ToughTongueBuildGhostLiveAvatarProviders.PremiumMinutesMultiplier) failures.Add("premium-live-avatar-binding-cost-invalid");
        if (!binding.ProviderManagedLipSynchronization) failures.Add("premium-live-avatar-binding-animation-unverified");
        if (receipt is not null && failures.Count == 0 && binding.SchemaReceiptDigest != DigestReceipt(receipt)) failures.Add("premium-live-avatar-binding-schema-receipt-mismatch");
        if (failures.Count == 0 && binding.ContractDigest != Digest(BindingAuthority(binding))) failures.Add("premium-live-avatar-binding-contract-digest-invalid");
        return Ordered(failures);
    }

    public static string DigestReceipt(BuildGhostToughTonguePremiumLiveAvatarSchemaReceipt receipt)
        => Digest(new JsonObject
        {
            ["schema"] = receipt.Schema,
            ["providerNamespace"] = receipt.ProviderNamespace,
            ["deploymentId"] = receipt.DeploymentId,
            ["studioBundleUrl"] = receipt.StudioBundleUrl.AbsoluteUri,
            ["studioBundleDigest"] = receipt.StudioBundleDigest,
            ["studioBundleBytes"] = receipt.StudioBundleBytes,
            ["scenarioRuntimeBundleUrl"] = receipt.ScenarioRuntimeBundleUrl.AbsoluteUri,
            ["scenarioRuntimeBundleDigest"] = receipt.ScenarioRuntimeBundleDigest,
            ["scenarioRuntimeBundleBytes"] = receipt.ScenarioRuntimeBundleBytes,
            ["sessionCreateBundleUrl"] = receipt.SessionCreateBundleUrl.AbsoluteUri,
            ["sessionCreateBundleDigest"] = receipt.SessionCreateBundleDigest,
            ["sessionCreateBundleBytes"] = receipt.SessionCreateBundleBytes,
            ["scenarioLiveAvatarIdFieldPath"] = receipt.ScenarioLiveAvatarIdFieldPath,
            ["scenarioLiveAvatarProviderFieldPath"] = receipt.ScenarioLiveAvatarProviderFieldPath,
            ["runtimeEnabledFieldPath"] = receipt.RuntimeEnabledFieldPath,
            ["runtimeAvatarIdFieldPath"] = receipt.RuntimeAvatarIdFieldPath,
            ["runtimeProviderFieldPath"] = receipt.RuntimeProviderFieldPath,
            ["requiredModelProvider"] = receipt.RequiredModelProvider,
            ["allowedProviders"] = new JsonArray(receipt.AllowedProviders.Select(static value => JsonValue.Create(value)).ToArray()),
            ["anamMinutesMultiplier"] = receipt.AnamMinutesMultiplier,
            ["heyGenMinutesMultiplier"] = receipt.HeyGenMinutesMultiplier,
            ["providerManagedLipSynchronizationAdvertised"] = receipt.ProviderManagedLipSynchronizationAdvertised,
            ["observedAtUtc"] = receipt.ObservedAtUtc.ToUniversalTime().ToString("O")
        });

    public static string Read(JsonObject payload, string fieldPath)
    {
        if (!IsSafeFieldPath(fieldPath)) return string.Empty;
        JsonNode? current = payload;
        foreach (string segment in fieldPath.Split('.', StringSplitOptions.None))
        {
            current = current is JsonObject currentObject ? currentObject[segment] : null;
        }
        return current is JsonValue leaf && leaf.TryGetValue(out string? value)
            ? value?.Trim() ?? string.Empty
            : string.Empty;
    }

    private static void RequireBundle(
        Uri? actualUrl,
        string actualDigest,
        long actualBytes,
        string expectedUrl,
        string expectedDigest,
        long expectedBytes,
        string label,
        ICollection<string> failures)
    {
        if (actualUrl?.AbsoluteUri != expectedUrl) failures.Add($"premium-live-avatar-{label}-bundle-url-drift");
        if (actualDigest != expectedDigest) failures.Add($"premium-live-avatar-{label}-bundle-digest-drift");
        if (actualBytes != expectedBytes) failures.Add($"premium-live-avatar-{label}-bundle-size-drift");
    }

    private static JsonObject BindingAuthority(BuildGhostToughTonguePremiumLiveAvatarBinding binding)
        => new()
        {
            ["schema"] = binding.Schema,
            ["provider"] = binding.Provider,
            ["providerAvatarIdDigest"] = binding.ProviderAvatarIdDigest,
            ["requiredModelProvider"] = binding.RequiredModelProvider,
            ["minutesMultiplier"] = binding.MinutesMultiplier,
            ["providerManagedLipSynchronization"] = binding.ProviderManagedLipSynchronization,
            ["schemaReceiptDigest"] = binding.SchemaReceiptDigest
        };

    private static bool IsSafeProviderAvatarId(string? value)
        => value is { Length: >= 1 and <= 256 }
            && value.All(static character => char.IsAsciiLetterOrDigit(character) || character is '-' or '_' or '.' or ':');

    private static bool IsSafeFieldPath(string? value)
        => value is { Length: >= 3 and <= 128 }
            && value.Split('.', StringSplitOptions.None).All(static segment => segment.Length is >= 1 and <= 64
                && segment.All(static character => char.IsAsciiLetterOrDigit(character) || character is '_' or '-'));

    private static IReadOnlyList<string> Ordered(IEnumerable<string> failures)
        => failures.Distinct(StringComparer.Ordinal).OrderBy(static value => value, StringComparer.Ordinal).ToArray();

    private static string DigestText(string value)
        => $"sha256:{Convert.ToHexString(SHA256.HashData(System.Text.Encoding.UTF8.GetBytes(value))).ToLowerInvariant()}";

    private static string Digest(JsonNode node)
        => $"sha256:{Convert.ToHexString(SHA256.HashData(JsonSerializer.SerializeToUtf8Bytes(node, new JsonSerializerOptions { WriteIndented = false }))).ToLowerInvariant()}";
}

public static class BuildGhostToughTongueCustomFunctionContract
{
    public const string ProviderNamespace = "tough-tongue";
    public const string VerifiedDeploymentId = "dpl_DKFDJRMr7tN6xHLYuhLbBaEVDZi8";
    public const string ServiceChunkName = "11.vljf9wpdc_.js";
    public const string ServiceChunkDigest = "sha256:6762f11c1970fa1c313d893176fb77eee6fddc4060d49413842ccc46ce88f145";
    public const long ServiceChunkBytes = 43_371;
    public const string StudioChunkName = "022lmhmvlj3gq.js";
    public const string StudioChunkDigest = "sha256:c1d1c9633f2645346b73165f9603b3491e266e568b2df3cc775014fc7b2c60a0";
    public const long StudioChunkBytes = 475_108;
    public const string ScenarioServiceChunkName = "0s5z52s8kf9d4.js";
    public const string ScenarioServiceChunkDigest = "sha256:4cd1339b7470d41c60ece066b7c8555f6392395412bff102949bd8e0ab824a51";
    public const long ScenarioServiceChunkBytes = 112_602;
    public const string RuntimeChunkName = "10w5gkzd~f23z.js";
    public const string RuntimeChunkDigest = "sha256:8a3427924a4eae6f5c7d97c10124178272db17d7c6b6b6189c0bdec78e0dfd14";
    public const long RuntimeChunkBytes = 219_531;
    public const string ApiBaseUrl = "https://api.toughtongueai.com/api/";
    public const string ListPath = "custom-functions/";
    public const string ByScenarioPathTemplate = "custom-functions/by-scenario/{scenario}";
    public const string CreatePath = "custom-functions/";
    public const string UpdatePathTemplate = "custom-functions/{id}";
    public const string ExecutePathTemplate = "custom-functions/{id}/execute";
    public const string DeletePathTemplate = "custom-functions/{id}";
    public const string ScenarioUpsertPath = "scenarios/upsert";
    public const string ScenarioAttachmentField = "custom_function_ids";
    public const string RuntimeRegistrationPrefix = "api_";
    public const string DynamicAuthorizationBlocker =
        "tough-tongue-stored-header-dynamic-argument-interpolation-unproven";
    public const string AuthenticatedLibraryReadBlocker =
        "tough-tongue-custom-function-library-bearer-read-unverified";
    public const string MissingBindingBlocker =
        "tough-tongue-custom-function-binding-missing-or-unverified";
    public const string ScenarioMutationPublicApiBlocker =
        "tough-tongue-scenario-upsert-public-api-contract-undocumented";

    public static readonly IReadOnlyList<string> CreateFields =
    [
        "name", "description", "function_type", "method", "url", "timeout_ms",
        "headers", "query_params", "parameters"
    ];

    public static readonly IReadOnlyList<string> ReturnedFields =
    [
        "id", "name", "description", "function_type", "method", "url",
        "timeout_ms", "headers", "query_params", "parameters"
    ];

    public static IReadOnlyList<string> ValidateLibrarySchema(
        BuildGhostToughTongueCustomFunctionLibrarySchemaReceipt? receipt)
    {
        if (receipt is null) return ["tough-tongue-custom-function-library-schema-receipt-missing"];
        List<string> failures = [];
        if (receipt.Schema != ToughTongueBuildGhostContractVersions.CustomFunctionLibrarySchemaReceiptV1) failures.Add("custom-function-library-schema-version-invalid");
        if (receipt.ProviderNamespace != ProviderNamespace) failures.Add("custom-function-library-provider-namespace-invalid");
        if (receipt.DeploymentId != VerifiedDeploymentId) failures.Add("custom-function-library-deployment-drift");
        RequireEvidence(receipt.ServiceChunkName, receipt.ServiceChunkDigest, receipt.ServiceChunkBytes, ServiceChunkName, ServiceChunkDigest, ServiceChunkBytes, "service", failures);
        RequireEvidence(receipt.StudioChunkName, receipt.StudioChunkDigest, receipt.StudioChunkBytes, StudioChunkName, StudioChunkDigest, StudioChunkBytes, "studio", failures);
        RequireEvidence(receipt.ScenarioServiceChunkName, receipt.ScenarioServiceChunkDigest, receipt.ScenarioServiceChunkBytes, ScenarioServiceChunkName, ScenarioServiceChunkDigest, ScenarioServiceChunkBytes, "scenario-service", failures);
        RequireEvidence(receipt.RuntimeChunkName, receipt.RuntimeChunkDigest, receipt.RuntimeChunkBytes, RuntimeChunkName, RuntimeChunkDigest, RuntimeChunkBytes, "runtime", failures);
        if (receipt.ApiBaseUri?.AbsoluteUri != ApiBaseUrl) failures.Add("custom-function-api-base-drift");
        if (receipt.ListPath != ListPath) failures.Add("custom-function-list-path-drift");
        if (receipt.ByScenarioPathTemplate != ByScenarioPathTemplate) failures.Add("custom-function-by-scenario-path-drift");
        if (receipt.CreatePath != CreatePath) failures.Add("custom-function-create-path-drift");
        if (receipt.UpdatePathTemplate != UpdatePathTemplate) failures.Add("custom-function-update-path-drift");
        if (receipt.ExecutePathTemplate != ExecutePathTemplate) failures.Add("custom-function-execute-path-drift");
        if (receipt.DeletePathTemplate != DeletePathTemplate) failures.Add("custom-function-delete-path-drift");
        if (receipt.ScenarioUpsertPath != ScenarioUpsertPath) failures.Add("custom-function-scenario-upsert-path-drift");
        if (!receipt.CreateFields.SequenceEqual(CreateFields, StringComparer.Ordinal)) failures.Add("custom-function-create-fields-drift");
        if (!receipt.ReturnedFields.SequenceEqual(ReturnedFields, StringComparer.Ordinal)) failures.Add("custom-function-returned-fields-drift");
        if (receipt.ScenarioAttachmentField != ScenarioAttachmentField) failures.Add("custom-function-scenario-attachment-field-drift");
        if (receipt.RuntimeRegistrationPrefix != RuntimeRegistrationPrefix) failures.Add("custom-function-runtime-registration-prefix-drift");
        if (receipt.ObservedAtUtc == default) failures.Add("custom-function-library-observed-at-invalid");
        return Ordered(failures);
    }

    public static IReadOnlyList<string> ValidateAuthenticatedRead(
        BuildGhostToughTongueCustomFunctionLibraryReadReceipt? receipt,
        string expectedAccountRefDigest)
    {
        if (receipt is null) return [AuthenticatedLibraryReadBlocker];
        List<string> failures = [];
        if (receipt.Schema != ToughTongueBuildGhostContractVersions.CustomFunctionLibraryReadReceiptV1) failures.Add("custom-function-library-read-version-invalid");
        if (receipt.Endpoint?.AbsoluteUri != $"{ApiBaseUrl}{ListPath}") failures.Add("custom-function-library-read-endpoint-invalid");
        if (receipt.Method != "GET") failures.Add("custom-function-library-read-method-invalid");
        if (!IsSafeSlotLabel(receipt.SelectedSlotLabel)) failures.Add("custom-function-library-read-slot-invalid");
        if (!IsSha256(expectedAccountRefDigest) || receipt.AccountRefDigest != expectedAccountRefDigest) failures.Add("custom-function-library-read-account-ref-mismatch");
        if (receipt.HttpStatus != 200) failures.Add(AuthenticatedLibraryReadBlocker);
        if (!receipt.JsonSchemaObserved
            || !receipt.ReturnedFields.SequenceEqual(ReturnedFields, StringComparer.Ordinal))
        {
            failures.Add("custom-function-library-read-schema-unverified");
        }
        if (!IsSha256(receipt.ProviderResponseDigest)) failures.Add("custom-function-library-read-response-digest-invalid");
        if (receipt.RawResponseExposed || receipt.RawIdsExposed || receipt.CredentialExposed) failures.Add("custom-function-library-read-redaction-invalid");
        if (receipt.ObservedAtUtc == default) failures.Add("custom-function-library-read-observed-at-invalid");
        return Ordered(failures);
    }

    public static IReadOnlyList<string> ValidateDynamicAuthorization(
        BuildGhostToughTongueDynamicAuthorizationReceipt? receipt,
        string? trustedReceiptDigest)
    {
        if (receipt is null || !IsSha256(trustedReceiptDigest)) return [DynamicAuthorizationBlocker];
        List<string> failures = [];
        if (receipt.Schema != ToughTongueBuildGhostContractVersions.CustomFunctionDynamicAuthorizationReceiptV1) failures.Add("custom-function-dynamic-auth-version-invalid");
        if (receipt.ProviderNamespace != ProviderNamespace) failures.Add("custom-function-dynamic-auth-provider-invalid");
        if (receipt.DeploymentId != VerifiedDeploymentId) failures.Add("custom-function-dynamic-auth-deployment-drift");
        if (!IsSafeChunkName(receipt.EvidenceSource) || !IsSha256(receipt.EvidenceDigest)) failures.Add("custom-function-dynamic-auth-evidence-invalid");
        if (receipt.HeaderName != "Authorization") failures.Add("custom-function-dynamic-auth-header-invalid");
        if (receipt.HeaderValueTemplate != "Bearer {{packet_access_key}}") failures.Add("custom-function-dynamic-auth-template-invalid");
        if (receipt.ArgumentName != "packet_access_key") failures.Add("custom-function-dynamic-auth-argument-invalid");
        if (receipt.InterpolationSemantics != "stored-header-values-interpolate-execute-args"
            || !receipt.StoredHeaderValuesInterpolateToolArguments)
        {
            failures.Add(DynamicAuthorizationBlocker);
        }
        if (receipt.ObservedAtUtc == default) failures.Add("custom-function-dynamic-auth-observed-at-invalid");
        if (failures.Count == 0 && DigestDynamicAuthorizationReceipt(receipt) != trustedReceiptDigest)
        {
            failures.Add("custom-function-dynamic-auth-receipt-untrusted");
        }
        return Ordered(failures);
    }

    public static BuildGhostToughTongueCustomFunctionDefinition CreateDefinition(
        BuildGhostPrivateToolDeploymentPackage deployment,
        BuildGhostToughTongueCustomFunctionLibrarySchemaReceipt? librarySchemaReceipt,
        BuildGhostToughTongueCustomFunctionLibraryReadReceipt? libraryReadReceipt,
        string expectedAccountRefDigest,
        BuildGhostToughTongueDynamicAuthorizationReceipt? dynamicAuthorizationReceipt = null,
        string? trustedDynamicAuthorizationReceiptDigest = null)
    {
        ArgumentNullException.ThrowIfNull(deployment);
        IReadOnlyList<string> schemaFailures = ValidateLibrarySchema(librarySchemaReceipt);
        IReadOnlyList<string> readFailures = ValidateAuthenticatedRead(libraryReadReceipt, expectedAccountRefDigest);
        IReadOnlyList<string> dynamicFailures = ValidateDynamicAuthorization(
            dynamicAuthorizationReceipt,
            trustedDynamicAuthorizationReceiptDigest);
        bool schemaVerified = schemaFailures.Count == 0;
        bool readVerified = readFailures.Count == 0;
        bool dynamicVerified = dynamicFailures.Count == 0;
        JsonObject payload = DefinitionPayload(deployment.Tool);
        string librarySchemaDigest = schemaVerified ? DigestLibrarySchemaReceipt(librarySchemaReceipt!) : string.Empty;
        string libraryReadDigest = readVerified ? DigestLibraryReadReceipt(libraryReadReceipt!) : string.Empty;
        string dynamicDigest = dynamicVerified ? DigestDynamicAuthorizationReceipt(dynamicAuthorizationReceipt!) : string.Empty;
        IReadOnlyList<string> blockers = Ordered(schemaFailures.Concat(readFailures).Concat(dynamicFailures));
        JsonObject authority = new()
        {
            ["schema"] = ToughTongueBuildGhostContractVersions.CustomFunctionDefinitionV1,
            ["payload"] = payload.DeepClone(),
            ["toolContractDigest"] = deployment.Tool.ContractDigest,
            ["toolDeploymentDigest"] = deployment.ContractDigest,
            ["librarySchemaReceiptDigest"] = librarySchemaDigest,
            ["libraryReadReceiptDigest"] = libraryReadDigest,
            ["dynamicAuthorizationReceiptDigest"] = dynamicDigest
        };
        return new BuildGhostToughTongueCustomFunctionDefinition(
            ToughTongueBuildGhostContractVersions.CustomFunctionDefinitionV1,
            payload,
            deployment.Tool.ContractDigest,
            deployment.ContractDigest,
            librarySchemaDigest,
            libraryReadDigest,
            dynamicDigest,
            schemaVerified,
            readVerified,
            dynamicVerified,
            blockers,
            Digest(authority));
    }

    public static JsonObject SerializeCreatePayload(BuildGhostToughTongueCustomFunctionDefinition definition)
    {
        ArgumentNullException.ThrowIfNull(definition);
        if (!definition.LibrarySchemaVerified
            || !definition.AuthenticatedLibraryReadVerified
            || !definition.DynamicAuthorizationVerified
            || definition.BlockingReasons.Count != 0
            || definition.ContractDigest != DefinitionDigest(definition)
            || !DefinitionPayloadShapeMatches(definition.Payload))
        {
            throw new InvalidDataException("custom-function-create-blocked-unverified-contract");
        }
        return (JsonObject)definition.Payload.DeepClone();
    }

    public static BuildGhostToughTongueCustomFunctionBinding CreateBinding(
        BuildGhostToughTongueCustomFunctionDefinition definition,
        string providerCustomFunctionId,
        int storedReadHttpStatus,
        JsonObject? storedFunction,
        string storedResponseDigest,
        DateTimeOffset observedAtUtc)
    {
        ArgumentNullException.ThrowIfNull(definition);
        if (!IsSafeOpaqueId(providerCustomFunctionId)
            || storedReadHttpStatus != 200
            || !IsSha256(storedResponseDigest)
            || observedAtUtc == default
            || !definition.LibrarySchemaVerified
            || !definition.AuthenticatedLibraryReadVerified
            || !definition.DynamicAuthorizationVerified
            || definition.BlockingReasons.Count != 0
            || definition.ContractDigest != DefinitionDigest(definition))
        {
            throw new ArgumentException("custom-function-binding-read-receipt-invalid");
        }
        bool storedFieldsMatch = StoredFunctionMatches(storedFunction, definition.Payload, providerCustomFunctionId);
        if (!storedFieldsMatch) throw new ArgumentException("custom-function-stored-fields-mismatch", nameof(storedFunction));
        string idDigest = DigestText(providerCustomFunctionId);
        JsonObject authority = BindingAuthority(
            idDigest,
            definition,
            storedReadHttpStatus,
            storedFieldsMatch,
            storedResponseDigest,
            observedAtUtc);
        return new BuildGhostToughTongueCustomFunctionBinding(
            ToughTongueBuildGhostContractVersions.CustomFunctionBindingV1,
            providerCustomFunctionId,
            idDigest,
            definition.ContractDigest,
            definition.ToolContractDigest,
            definition.ToolDeploymentDigest,
            definition.LibrarySchemaReceiptDigest,
            definition.LibraryReadReceiptDigest,
            definition.DynamicAuthorizationReceiptDigest,
            storedReadHttpStatus,
            storedFieldsMatch,
            storedResponseDigest,
            RawResponseExposed: false,
            RawIdsExposed: false,
            CredentialExposed: false,
            observedAtUtc,
            Digest(authority));
    }

    public static IReadOnlyList<string> ValidateBinding(
        BuildGhostToughTongueCustomFunctionBinding? binding,
        BuildGhostPrivateToolDeploymentPackage deployment)
    {
        if (binding is null) return [MissingBindingBlocker];
        List<string> failures = [];
        if (binding.Schema != ToughTongueBuildGhostContractVersions.CustomFunctionBindingV1) failures.Add("custom-function-binding-version-invalid");
        if (!IsSafeOpaqueId(binding.ProviderCustomFunctionId)
            || binding.ProviderCustomFunctionIdDigest != DigestText(binding.ProviderCustomFunctionId)) failures.Add("custom-function-binding-id-invalid");
        if (!IsSha256(binding.DefinitionContractDigest)) failures.Add("custom-function-definition-digest-invalid");
        if (binding.ToolContractDigest != deployment.Tool.ContractDigest) failures.Add("custom-function-binding-tool-digest-mismatch");
        if (binding.ToolDeploymentDigest != deployment.ContractDigest) failures.Add("custom-function-binding-deployment-digest-mismatch");
        if (!IsSha256(binding.LibrarySchemaReceiptDigest)) failures.Add("custom-function-binding-library-schema-digest-invalid");
        if (!IsSha256(binding.LibraryReadReceiptDigest)) failures.Add("custom-function-binding-library-read-digest-invalid");
        if (!IsSha256(binding.DynamicAuthorizationReceiptDigest)) failures.Add("custom-function-binding-dynamic-auth-digest-invalid");
        if (binding.StoredReadHttpStatus != 200 || !binding.StoredFieldsExactMatch || !IsSha256(binding.StoredResponseDigest)) failures.Add("custom-function-binding-stored-read-unverified");
        if (binding.RawResponseExposed || binding.RawIdsExposed || binding.CredentialExposed) failures.Add("custom-function-binding-redaction-invalid");
        if (binding.ObservedAtUtc == default) failures.Add("custom-function-binding-observed-at-invalid");
        if (failures.Count == 0
            && binding.ContractDigest != Digest(BindingAuthority(
                binding.ProviderCustomFunctionIdDigest,
                binding.DefinitionContractDigest,
                binding.ToolContractDigest,
                binding.ToolDeploymentDigest,
                binding.LibrarySchemaReceiptDigest,
                binding.LibraryReadReceiptDigest,
                binding.DynamicAuthorizationReceiptDigest,
                binding.StoredReadHttpStatus,
                binding.StoredFieldsExactMatch,
                binding.StoredResponseDigest,
                binding.ObservedAtUtc)))
        {
            failures.Add("custom-function-binding-contract-digest-invalid");
        }
        return Ordered(failures);
    }

    public static BuildGhostToughTongueCustomFunctionAttachmentReceipt CreateAttachmentReceipt(
        string scenarioId,
        JsonObject? scenario,
        int scenarioReadHttpStatus,
        JsonArray? byScenarioFunctions,
        int byScenarioReadHttpStatus,
        BuildGhostToughTongueCustomFunctionBinding binding,
        BuildGhostToughTongueCustomFunctionDefinition definition,
        DateTimeOffset observedAtUtc)
    {
        ArgumentNullException.ThrowIfNull(binding);
        ArgumentNullException.ThrowIfNull(definition);
        List<string> blockers = [];
        if (!IsObjectId(scenarioId)) blockers.Add("custom-function-attachment-scenario-id-invalid");
        bool definitionMatch = BindingMatchesDefinition(binding, definition)
            && binding.DefinitionContractDigest == definition.ContractDigest
            && definition.ContractDigest == DefinitionDigest(definition)
            && definition.BlockingReasons.Count == 0
            && definition.LibrarySchemaVerified
            && definition.AuthenticatedLibraryReadVerified
            && definition.DynamicAuthorizationVerified;
        if (!definitionMatch) blockers.Add("custom-function-attachment-definition-unverified");
        bool scenarioMatch = scenarioReadHttpStatus == 200
            && ExactIdArray(scenario?[ScenarioAttachmentField] as JsonArray, binding.ProviderCustomFunctionId);
        bool byScenarioMatch = byScenarioReadHttpStatus == 200
            && definitionMatch
            && ExactReturnedFunctionArray(
                byScenarioFunctions,
                binding.ProviderCustomFunctionId,
                definition.Payload);
        if (!scenarioMatch) blockers.Add("custom-function-scenario-attachment-readback-mismatch");
        if (!byScenarioMatch) blockers.Add("custom-function-by-scenario-readback-mismatch");
        if (observedAtUtc == default) blockers.Add("custom-function-attachment-observed-at-invalid");
        string scenarioDigest = IsObjectId(scenarioId) ? DigestText(scenarioId) : string.Empty;
        JsonObject authority = AttachmentAuthority(
            scenarioDigest,
            binding,
            scenarioReadHttpStatus,
            scenarioMatch,
            byScenarioReadHttpStatus,
            byScenarioMatch,
            Ordered(blockers),
            observedAtUtc);
        return new BuildGhostToughTongueCustomFunctionAttachmentReceipt(
            ToughTongueBuildGhostContractVersions.CustomFunctionAttachmentReceiptV1,
            scenarioDigest,
            binding.ProviderCustomFunctionIdDigest,
            binding.DefinitionContractDigest,
            binding.ContractDigest,
            ScenarioAttachmentField,
            scenarioReadHttpStatus,
            scenarioMatch,
            byScenarioReadHttpStatus,
            byScenarioMatch,
            RawResponseExposed: false,
            RawIdsExposed: false,
            CredentialExposed: false,
            Ordered(blockers),
            observedAtUtc,
            Digest(authority));
    }

    public static IReadOnlyList<string> ValidateAttachmentReceipt(
        BuildGhostToughTongueCustomFunctionAttachmentReceipt? receipt,
        BuildGhostToughTongueCustomFunctionBinding binding)
    {
        ArgumentNullException.ThrowIfNull(binding);
        if (receipt is null) return ["custom-function-attachment-receipt-missing"];
        List<string> failures = [];
        if (receipt.Schema != ToughTongueBuildGhostContractVersions.CustomFunctionAttachmentReceiptV1) failures.Add("custom-function-attachment-version-invalid");
        if (!IsSha256(receipt.ScenarioIdDigest)) failures.Add("custom-function-attachment-scenario-digest-invalid");
        if (receipt.ProviderCustomFunctionIdDigest != binding.ProviderCustomFunctionIdDigest) failures.Add("custom-function-attachment-id-digest-mismatch");
        if (receipt.DefinitionContractDigest != binding.DefinitionContractDigest) failures.Add("custom-function-attachment-definition-digest-mismatch");
        if (receipt.BindingContractDigest != binding.ContractDigest) failures.Add("custom-function-attachment-binding-digest-mismatch");
        if (receipt.ScenarioAttachmentField != ScenarioAttachmentField) failures.Add("custom-function-attachment-field-drift");
        if (receipt.ScenarioReadHttpStatus != 200 || !receipt.ScenarioAttachmentExactMatch) failures.Add("custom-function-scenario-attachment-readback-mismatch");
        if (receipt.ByScenarioReadHttpStatus != 200 || !receipt.ByScenarioAttachmentExactMatch) failures.Add("custom-function-by-scenario-readback-mismatch");
        if (receipt.RawResponseExposed || receipt.RawIdsExposed || receipt.CredentialExposed) failures.Add("custom-function-attachment-redaction-invalid");
        if (receipt.BlockingReasons.Count != 0) failures.AddRange(receipt.BlockingReasons);
        if (receipt.ObservedAtUtc == default) failures.Add("custom-function-attachment-observed-at-invalid");
        if (failures.Count == 0
            && receipt.ContractDigest != Digest(AttachmentAuthority(
                receipt.ScenarioIdDigest,
                receipt.ProviderCustomFunctionIdDigest,
                receipt.DefinitionContractDigest,
                receipt.BindingContractDigest,
                receipt.ScenarioAttachmentField,
                receipt.ScenarioReadHttpStatus,
                receipt.ScenarioAttachmentExactMatch,
                receipt.ByScenarioReadHttpStatus,
                receipt.ByScenarioAttachmentExactMatch,
                receipt.BlockingReasons,
                receipt.ObservedAtUtc)))
        {
            failures.Add("custom-function-attachment-contract-digest-invalid");
        }
        return Ordered(failures);
    }

    public static string DigestLibrarySchemaReceipt(BuildGhostToughTongueCustomFunctionLibrarySchemaReceipt receipt)
        => Digest(JsonSerializer.SerializeToNode(receipt) ?? new JsonObject());

    public static string DigestLibraryReadReceipt(BuildGhostToughTongueCustomFunctionLibraryReadReceipt receipt)
        => Digest(JsonSerializer.SerializeToNode(receipt) ?? new JsonObject());

    public static string DigestDynamicAuthorizationReceipt(BuildGhostToughTongueDynamicAuthorizationReceipt receipt)
        => Digest(JsonSerializer.SerializeToNode(receipt) ?? new JsonObject());

    private static JsonObject DefinitionPayload(BuildGhostPrivateToolDefinition tool)
        => new()
        {
            ["name"] = tool.Name,
            ["description"] = tool.Description,
            ["function_type"] = "default",
            ["method"] = tool.HttpMethod,
            ["url"] = tool.Endpoint.AbsoluteUri,
            ["timeout_ms"] = checked(tool.TimeoutSeconds * 1_000),
            ["headers"] = new JsonObject
            {
                ["Authorization"] = "Bearer {{packet_access_key}}",
                ["X-Chummer-Build-Ghost-Tool-Contract"] = tool.ContractDigest
            },
            ["query_params"] = new JsonObject(),
            ["parameters"] = JsonNode.Parse(tool.BodySchemaJson)
        };

    private static bool DefinitionPayloadShapeMatches(JsonObject payload)
        => payload.Select(static pair => pair.Key).SequenceEqual(CreateFields, StringComparer.Ordinal)
            && Text(payload, "function_type") == "default"
            && Text(payload, "method") == "POST"
            && payload["headers"] is JsonObject headers
            && Text(headers, "Authorization") == "Bearer {{packet_access_key}}"
            && IsSha256(Text(headers, "X-Chummer-Build-Ghost-Tool-Contract"))
            && payload["query_params"] is JsonObject query && query.Count == 0
            && payload["parameters"] is JsonObject;

    private static bool StoredFunctionMatches(JsonObject? stored, JsonObject expected, string providerId)
    {
        if (stored is null || Text(stored, "id") != providerId) return false;
        foreach (string field in CreateFields)
        {
            if (!JsonNode.DeepEquals(stored[field], expected[field])) return false;
        }
        return true;
    }

    private static bool BindingMatchesDefinition(
        BuildGhostToughTongueCustomFunctionBinding binding,
        BuildGhostToughTongueCustomFunctionDefinition definition)
        => binding.Schema == ToughTongueBuildGhostContractVersions.CustomFunctionBindingV1
            && IsSafeOpaqueId(binding.ProviderCustomFunctionId)
            && binding.ProviderCustomFunctionIdDigest == DigestText(binding.ProviderCustomFunctionId)
            && binding.DefinitionContractDigest == definition.ContractDigest
            && binding.ToolContractDigest == definition.ToolContractDigest
            && binding.ToolDeploymentDigest == definition.ToolDeploymentDigest
            && binding.LibrarySchemaReceiptDigest == definition.LibrarySchemaReceiptDigest
            && binding.LibraryReadReceiptDigest == definition.LibraryReadReceiptDigest
            && binding.DynamicAuthorizationReceiptDigest == definition.DynamicAuthorizationReceiptDigest
            && binding.StoredReadHttpStatus == 200
            && binding.StoredFieldsExactMatch
            && IsSha256(binding.StoredResponseDigest)
            && !binding.RawResponseExposed
            && !binding.RawIdsExposed
            && !binding.CredentialExposed
            && binding.ObservedAtUtc != default
            && binding.ContractDigest == Digest(BindingAuthority(
                binding.ProviderCustomFunctionIdDigest,
                binding.DefinitionContractDigest,
                binding.ToolContractDigest,
                binding.ToolDeploymentDigest,
                binding.LibrarySchemaReceiptDigest,
                binding.LibraryReadReceiptDigest,
                binding.DynamicAuthorizationReceiptDigest,
                binding.StoredReadHttpStatus,
                binding.StoredFieldsExactMatch,
                binding.StoredResponseDigest,
                binding.ObservedAtUtc));

    private static string DefinitionDigest(BuildGhostToughTongueCustomFunctionDefinition definition)
        => Digest(new JsonObject
        {
            ["schema"] = definition.Schema,
            ["payload"] = definition.Payload.DeepClone(),
            ["toolContractDigest"] = definition.ToolContractDigest,
            ["toolDeploymentDigest"] = definition.ToolDeploymentDigest,
            ["librarySchemaReceiptDigest"] = definition.LibrarySchemaReceiptDigest,
            ["libraryReadReceiptDigest"] = definition.LibraryReadReceiptDigest,
            ["dynamicAuthorizationReceiptDigest"] = definition.DynamicAuthorizationReceiptDigest
        });

    private static JsonObject BindingAuthority(
        string idDigest,
        BuildGhostToughTongueCustomFunctionDefinition definition,
        int status,
        bool exactMatch,
        string responseDigest,
        DateTimeOffset observedAtUtc)
        => BindingAuthority(
            idDigest,
            definition.ContractDigest,
            definition.ToolContractDigest,
            definition.ToolDeploymentDigest,
            definition.LibrarySchemaReceiptDigest,
            definition.LibraryReadReceiptDigest,
            definition.DynamicAuthorizationReceiptDigest,
            status,
            exactMatch,
            responseDigest,
            observedAtUtc);

    private static JsonObject BindingAuthority(
        string idDigest,
        string definitionDigest,
        string toolDigest,
        string deploymentDigest,
        string schemaReceiptDigest,
        string readReceiptDigest,
        string dynamicReceiptDigest,
        int status,
        bool exactMatch,
        string responseDigest,
        DateTimeOffset observedAtUtc)
        => new()
        {
            ["schema"] = ToughTongueBuildGhostContractVersions.CustomFunctionBindingV1,
            ["providerCustomFunctionIdDigest"] = idDigest,
            ["definitionContractDigest"] = definitionDigest,
            ["toolContractDigest"] = toolDigest,
            ["toolDeploymentDigest"] = deploymentDigest,
            ["librarySchemaReceiptDigest"] = schemaReceiptDigest,
            ["libraryReadReceiptDigest"] = readReceiptDigest,
            ["dynamicAuthorizationReceiptDigest"] = dynamicReceiptDigest,
            ["storedReadHttpStatus"] = status,
            ["storedFieldsExactMatch"] = exactMatch,
            ["storedResponseDigest"] = responseDigest,
            ["observedAtUtc"] = observedAtUtc.ToUniversalTime().ToString("O")
        };

    private static JsonObject AttachmentAuthority(
        string scenarioDigest,
        BuildGhostToughTongueCustomFunctionBinding binding,
        int scenarioStatus,
        bool scenarioMatch,
        int byScenarioStatus,
        bool byScenarioMatch,
        IReadOnlyList<string> blockers,
        DateTimeOffset observedAtUtc)
        => AttachmentAuthority(
            scenarioDigest,
            binding.ProviderCustomFunctionIdDigest,
            binding.DefinitionContractDigest,
            binding.ContractDigest,
            ScenarioAttachmentField,
            scenarioStatus,
            scenarioMatch,
            byScenarioStatus,
            byScenarioMatch,
            blockers,
            observedAtUtc);

    private static JsonObject AttachmentAuthority(
        string scenarioDigest,
        string providerIdDigest,
        string definitionDigest,
        string bindingDigest,
        string attachmentField,
        int scenarioStatus,
        bool scenarioMatch,
        int byScenarioStatus,
        bool byScenarioMatch,
        IReadOnlyList<string> blockers,
        DateTimeOffset observedAtUtc)
        => new()
        {
            ["schema"] = ToughTongueBuildGhostContractVersions.CustomFunctionAttachmentReceiptV1,
            ["scenarioIdDigest"] = scenarioDigest,
            ["providerCustomFunctionIdDigest"] = providerIdDigest,
            ["definitionContractDigest"] = definitionDigest,
            ["bindingContractDigest"] = bindingDigest,
            ["scenarioAttachmentField"] = attachmentField,
            ["scenarioReadHttpStatus"] = scenarioStatus,
            ["scenarioAttachmentExactMatch"] = scenarioMatch,
            ["byScenarioReadHttpStatus"] = byScenarioStatus,
            ["byScenarioAttachmentExactMatch"] = byScenarioMatch,
            ["blockingReasons"] = new JsonArray(blockers.Select(static reason => JsonValue.Create(reason)).ToArray()),
            ["observedAtUtc"] = observedAtUtc.ToUniversalTime().ToString("O")
        };

    private static void RequireEvidence(
        string actualName,
        string actualDigest,
        long actualBytes,
        string expectedName,
        string expectedDigest,
        long expectedBytes,
        string label,
        ICollection<string> failures)
    {
        if (actualName != expectedName) failures.Add($"custom-function-{label}-chunk-name-drift");
        if (actualDigest != expectedDigest) failures.Add($"custom-function-{label}-chunk-digest-drift");
        if (actualBytes != expectedBytes) failures.Add($"custom-function-{label}-chunk-size-drift");
    }

    private static bool ExactIdArray(JsonArray? values, string expected)
        => values is { Count: 1 }
            && values[0] is JsonValue value
            && value.TryGetValue(out string? actual)
            && actual == expected;

    private static bool ExactReturnedFunctionArray(
        JsonArray? values,
        string expectedId,
        JsonObject expectedDefinition)
        => values is { Count: 1 }
            && values[0] is JsonObject row
            && StoredFunctionMatches(row, expectedDefinition, expectedId);

    private static bool IsObjectId(string? value)
        => value is { Length: 24 }
            && value.All(static character => character is >= '0' and <= '9' or >= 'a' and <= 'f');

    private static bool IsSafeOpaqueId(string? value)
        => value is { Length: >= 1 and <= 128 }
            && value.All(static character => char.IsAsciiLetterOrDigit(character) || character is '-' or '_');

    private static bool IsSafeChunkName(string? value)
        => value is { Length: >= 4 and <= 128 }
            && value.EndsWith(".js", StringComparison.Ordinal)
            && value.All(static character => char.IsAsciiLetterOrDigit(character) || character is '.' or '-' or '_' or '~');

    private static bool IsSafeSlotLabel(string? value)
        => value is { Length: >= 3 and <= 64 }
            && value.All(static character => char.IsAsciiLetterOrDigit(character) || character is '-');

    private static bool IsSha256(string? value)
        => value is { Length: 71 }
            && value.StartsWith("sha256:", StringComparison.Ordinal)
            && value.AsSpan(7).ToString().All(static character => character is >= '0' and <= '9' or >= 'a' and <= 'f');

    private static string Text(JsonObject parent, string property)
        => parent[property] is JsonValue value && value.TryGetValue(out string? text)
            ? text?.Trim() ?? string.Empty
            : string.Empty;

    private static IReadOnlyList<string> Ordered(IEnumerable<string> failures)
        => failures.Distinct(StringComparer.Ordinal).OrderBy(static reason => reason, StringComparer.Ordinal).ToArray();

    private static string DigestText(string value)
        => $"sha256:{Convert.ToHexString(SHA256.HashData(System.Text.Encoding.UTF8.GetBytes(value))).ToLowerInvariant()}";

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
        BuildGhostToughTongueCustomFunctionBinding? customFunctionBinding = null)
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
        IReadOnlyList<string> customFunctionBindingFailures =
            BuildGhostToughTongueCustomFunctionContract.ValidateBinding(customFunctionBinding, deployment);
        bool customFunctionBindingReadVerified = customFunctionBindingFailures.Count == 0;
        string customFunctionBindingDigest = customFunctionBindingReadVerified
            ? customFunctionBinding!.ContractDigest
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
            [BuildGhostToughTongueCustomFunctionContract.ScenarioAttachmentField] =
                customFunctionBindingReadVerified
                    ? new JsonArray(customFunctionBinding!.ProviderCustomFunctionId)
                    : new JsonArray(),
            ["tools_config"] = new JsonObject
            {
                ["tools"] = new JsonObject
                {
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
                ["custom_function_binding_digest"] = customFunctionBindingDigest,
                ["custom_function_id_digest"] = customFunctionBindingReadVerified ? customFunctionBinding!.ProviderCustomFunctionIdDigest : string.Empty,
                ["custom_function_definition_digest"] = customFunctionBindingReadVerified ? customFunctionBinding!.DefinitionContractDigest : string.Empty,
                ["custom_function_library_schema_receipt_digest"] = customFunctionBindingReadVerified ? customFunctionBinding!.LibrarySchemaReceiptDigest : string.Empty,
                ["custom_function_library_read_receipt_digest"] = customFunctionBindingReadVerified ? customFunctionBinding!.LibraryReadReceiptDigest : string.Empty,
                ["custom_function_dynamic_authorization_receipt_digest"] = customFunctionBindingReadVerified ? customFunctionBinding!.DynamicAuthorizationReceiptDigest : string.Empty,
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
            customFunctionBinding,
            customFunctionBindingDigest,
            customFunctionBindingReadVerified,
            scenarioSchemaFailures.Concat(customFunctionBindingFailures)
                .Distinct(StringComparer.Ordinal)
                .OrderBy(static reason => reason, StringComparer.Ordinal)
                .ToArray(),
            contractDigest);
    }

    public static ToughTongueBuildGhostScenarioCandidate CreatePrivateRookPremiumLiveAvatarCandidate(
        BuildGhostPrivateToolDeploymentPackage deployment,
        Uri avatarUrl,
        BuildGhostCascadePrivateVoiceBinding runtimeBinding,
        BuildGhostToughTonguePremiumLiveAvatarBinding liveAvatarBinding,
        BuildGhostToughTonguePremiumLiveAvatarSchemaReceipt? liveAvatarSchemaReceipt,
        BuildGhostToughTongueCartesiaScenarioSchemaReceipt? scenarioSchemaReceipt = null,
        BuildGhostToughTongueCustomFunctionBinding? customFunctionBinding = null)
    {
        ArgumentNullException.ThrowIfNull(liveAvatarBinding);
        ToughTongueBuildGhostScenarioCandidate candidate = CreatePrivateRookCandidate(
            deployment,
            avatarUrl,
            runtimeBinding,
            scenarioSchemaReceipt,
            customFunctionBinding);
        IReadOnlyList<string> liveAvatarFailures =
            BuildGhostToughTonguePremiumLiveAvatarSchemaContract.ValidateBinding(
                liveAvatarBinding,
                liveAvatarSchemaReceipt);
        if (liveAvatarFailures.Count != 0)
        {
            return candidate with
            {
                LiveAvatarBinding = liveAvatarBinding,
                LiveAvatarBindingDigest = string.Empty,
                LiveAvatarSchemaVerified = false,
                LiveAvatarIdFieldPath = null,
                LiveAvatarProviderFieldPath = null,
                BlockingReasons = candidate.BlockingReasons.Concat(liveAvatarFailures)
                    .Distinct(StringComparer.Ordinal)
                    .OrderBy(static reason => reason, StringComparer.Ordinal)
                    .ToArray()
            };
        }

        JsonObject payload = (JsonObject)candidate.Payload.DeepClone();
        JsonObject appearance = Object(payload, "appearance");
        appearance["live_avatar_id"] = liveAvatarBinding.ProviderAvatarId;
        appearance["live_avatar_provider"] = liveAvatarBinding.Provider;
        JsonObject metadata = Object(payload, "user_metadata");
        metadata["live_avatar_provider"] = liveAvatarBinding.Provider;
        metadata["live_avatar_id_digest"] = liveAvatarBinding.ProviderAvatarIdDigest;
        metadata["live_avatar_schema_receipt_digest"] = liveAvatarBinding.SchemaReceiptDigest;
        metadata["live_avatar_binding_digest"] = liveAvatarBinding.ContractDigest;
        metadata["live_avatar_minutes_multiplier"] = liveAvatarBinding.MinutesMultiplier.ToString(
            System.Globalization.CultureInfo.InvariantCulture);
        metadata["live_avatar_render_posture"] = "provider-managed";
        metadata["local_lip_sync_posture"] = "deferred";
        metadata.Remove("scenario_contract_digest");
        string contractDigest = Digest(payload);
        metadata["scenario_contract_digest"] = contractDigest;
        return candidate with
        {
            Payload = payload,
            ContractDigest = contractDigest,
            LiveAvatarBinding = liveAvatarBinding,
            LiveAvatarBindingDigest = liveAvatarBinding.ContractDigest,
            LiveAvatarSchemaVerified = true,
            LiveAvatarIdFieldPath = liveAvatarSchemaReceipt!.ScenarioLiveAvatarIdFieldPath,
            LiveAvatarProviderFieldPath = liveAvatarSchemaReceipt.ScenarioLiveAvatarProviderFieldPath
        };
    }

    public static ToughTongueBuildGhostScenarioValidation Validate(
        JsonObject? scenario,
        ToughTongueBuildGhostScenarioCandidate expected)
    {
        ArgumentNullException.ThrowIfNull(expected);
        if (!expected.ProviderSchemaReadVerified
            || !expected.CustomFunctionBindingReadVerified
            || (expected.LiveAvatarBinding is not null && !expected.LiveAvatarSchemaVerified)
            || expected.BlockingReasons.Count != 0)
        {
            IReadOnlyList<string> blockers = expected.BlockingReasons.Count == 0
                ? expected.LiveAvatarBinding is not null && !expected.LiveAvatarSchemaVerified
                    ? [BuildGhostToughTonguePremiumLiveAvatarSchemaContract.MissingOrUnverifiedBlocker]
                    : [BuildGhostToughTongueCartesiaScenarioSchemaContract.MissingOrUnverifiedBlocker]
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
        if (expected.LiveAvatarBinding is not null)
        {
            if (expected.LiveAvatarIdFieldPath is null
                || BuildGhostToughTonguePremiumLiveAvatarSchemaContract.Read(
                    scenario,
                    expected.LiveAvatarIdFieldPath) != expected.LiveAvatarBinding.ProviderAvatarId)
            {
                reasons.Add("scenario-live-avatar-id-mismatch");
            }
            if (expected.LiveAvatarProviderFieldPath is null
                || BuildGhostToughTonguePremiumLiveAvatarSchemaContract.Read(
                    scenario,
                    expected.LiveAvatarProviderFieldPath) != expected.LiveAvatarBinding.Provider)
            {
                reasons.Add("scenario-live-avatar-provider-mismatch");
            }
        }
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
        if (expected.CustomFunctionBinding is null
            || !ExactStringArray(
                scenario[BuildGhostToughTongueCustomFunctionContract.ScenarioAttachmentField] as JsonArray,
                expected.CustomFunctionBinding.ProviderCustomFunctionId))
        {
            reasons.Add("custom-function-scenario-attachment-mismatch");
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
        RequireText(metadata, "custom_function_binding_digest", expected.CustomFunctionBindingDigest, "custom-function-binding-digest-mismatch", reasons);
        RequireText(metadata, "custom_function_id_digest", Text(expectedMetadata, "custom_function_id_digest"), "custom-function-id-digest-mismatch", reasons);
        RequireText(metadata, "custom_function_definition_digest", Text(expectedMetadata, "custom_function_definition_digest"), "custom-function-definition-digest-mismatch", reasons);
        RequireText(metadata, "custom_function_library_schema_receipt_digest", Text(expectedMetadata, "custom_function_library_schema_receipt_digest"), "custom-function-library-schema-receipt-digest-mismatch", reasons);
        RequireText(metadata, "custom_function_library_read_receipt_digest", Text(expectedMetadata, "custom_function_library_read_receipt_digest"), "custom-function-library-read-receipt-digest-mismatch", reasons);
        RequireText(metadata, "custom_function_dynamic_authorization_receipt_digest", Text(expectedMetadata, "custom_function_dynamic_authorization_receipt_digest"), "custom-function-dynamic-authorization-receipt-digest-mismatch", reasons);
        RequireText(metadata, "runtime_binding_digest", Text(expectedMetadata, "runtime_binding_digest"), "runtime-binding-digest-mismatch", reasons);
        RequireText(metadata, "voice_release_digest", Text(expectedMetadata, "voice_release_digest"), "voice-release-digest-mismatch", reasons);
        RequireText(metadata, "voice_read_receipt_digest", Text(expectedMetadata, "voice_read_receipt_digest"), "voice-read-receipt-digest-mismatch", reasons);
        RequireText(metadata, "tts_provider", ToughTongueBuildGhostVoiceProviders.CartesiaTtsProvider, "scenario-tts-provider-metadata-mismatch", reasons);
        RequireText(metadata, "provider_namespace", ToughTongueBuildGhostVoiceProviders.CartesiaNamespace, "scenario-provider-namespace-mismatch", reasons);
        RequireText(metadata, "tts_provider_schema_receipt_digest", Text(expectedMetadata, "tts_provider_schema_receipt_digest"), "scenario-tts-provider-schema-receipt-digest-mismatch", reasons);
        RequireText(metadata, "scenario_contract_digest", expected.ContractDigest, "scenario-contract-digest-mismatch", reasons);
        RequireText(metadata, "supported_locales", string.Join(',', CanonicalLocales), "scenario-locales-mismatch", reasons);
        RequireText(metadata, "release_channel", "private-nonproduction-candidate", "scenario-release-channel-invalid", reasons);
        if (expected.LiveAvatarBinding is not null)
        {
            RequireText(metadata, "live_avatar_provider", expected.LiveAvatarBinding.Provider, "scenario-live-avatar-provider-metadata-mismatch", reasons);
            RequireText(metadata, "live_avatar_id_digest", expected.LiveAvatarBinding.ProviderAvatarIdDigest, "scenario-live-avatar-id-digest-mismatch", reasons);
            RequireText(metadata, "live_avatar_schema_receipt_digest", expected.LiveAvatarBinding.SchemaReceiptDigest, "scenario-live-avatar-schema-receipt-digest-mismatch", reasons);
            RequireText(metadata, "live_avatar_binding_digest", expected.LiveAvatarBindingDigest, "scenario-live-avatar-binding-digest-mismatch", reasons);
            RequireText(metadata, "live_avatar_minutes_multiplier", expected.LiveAvatarBinding.MinutesMultiplier.ToString(System.Globalization.CultureInfo.InvariantCulture), "scenario-live-avatar-cost-mismatch", reasons);
            RequireText(metadata, "live_avatar_render_posture", "provider-managed", "scenario-live-avatar-render-posture-invalid", reasons);
            RequireText(metadata, "local_lip_sync_posture", "deferred", "scenario-local-lip-sync-posture-invalid", reasons);
        }

        return new ToughTongueBuildGhostScenarioValidation(
            reasons.Count == 0,
            scenarioId,
            reasons.Distinct(StringComparer.Ordinal).OrderBy(static reason => reason, StringComparer.Ordinal).ToArray());
    }

    public static JsonObject SerializeCreatePayload(ToughTongueBuildGhostScenarioCandidate candidate)
    {
        ArgumentNullException.ThrowIfNull(candidate);
        if (!candidate.ProviderSchemaReadVerified
            || !candidate.CustomFunctionBindingReadVerified
            || candidate.BlockingReasons.Count != 0)
        {
            throw new InvalidDataException("scenario-create-payload-provider-schema-unverified");
        }
        if (candidate.CustomFunctionBinding is null
            || !ExactStringArray(
                candidate.Payload[BuildGhostToughTongueCustomFunctionContract.ScenarioAttachmentField] as JsonArray,
                candidate.CustomFunctionBinding.ProviderCustomFunctionId)
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

    private static bool ExactStringArray(JsonArray? values, string expected)
        => values is { Count: 1 }
            && values[0] is JsonValue value
            && value.TryGetValue(out string? actual)
            && actual == expected;

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

    public Task<(ToughTongueBuildGhostScenarioValidation Validation, string? ScenarioId)> CreatePrivateCandidateAsync(
        ToughTongueBuildGhostScenarioCandidate candidate,
        string credential,
        CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(candidate);
        ToughTongueBuildGhostScenarioValidation? blocked = BlockedCandidate(candidate);
        if (blocked is not null) return Task.FromResult<(ToughTongueBuildGhostScenarioValidation, string?)>((blocked, null));
        return Task.FromResult<(ToughTongueBuildGhostScenarioValidation, string?)>((
            new ToughTongueBuildGhostScenarioValidation(
                false,
                null,
                [BuildGhostToughTongueCustomFunctionContract.ScenarioMutationPublicApiBlocker]),
            null));
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
            && candidate.CustomFunctionBindingReadVerified
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
            || !expected.CustomFunctionBindingReadVerified
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
