using System.Text.Json.Nodes;
using System.Text.Json.Serialization;

namespace Chummer.Run.Contracts.BuildGhost;

public static class ToughTongueBuildGhostContractVersions
{
    public const string AnalysisV1 = "chummer.build_ghost_analysis.v1";
    public const string ProviderAnswerV1 = "chummer.build_ghost_provider_answer.v1";
    public const string RequestV1 = "chummer.tough_tongue.build_ghost_request.v1";
    public const string ReceiptV1 = "chummer.tough_tongue.build_ghost_receipt.v1";
    public const string PersonaReleaseV1 = "chummer.build_ghost_persona_release.v1";
    public const string StockAvatarBindingV1 = "chummer.tough_tongue.stock_avatar_binding.v1";
    public const string StockAvatarReadbackReceiptV1 = "chummer.tough_tongue.stock_avatar_readback_receipt.v1";
    public const string ScenarioContractV1 = "chummer.tough_tongue.build_ghost_scenario.v1";
    public const string ScenarioContractV2 = "chummer.tough_tongue.build_ghost_scenario.v2";
    public const string ToolContractV1 = "chummer.tough_tongue.build_ghost_tool.v1";
    public const string PrivateToolContractV1 = "chummer.build_ghost.private_tool.v1";
    public const string PrivateToolContractV2 = "chummer.build_ghost.private_tool.v2";
    public const string PrivateToolRequestV2 = "chummer.build_ghost.private_tool_request.v2";
    public const string PrivateToolDeploymentV1 = "chummer.build_ghost.private_tool_deployment.v1";
    public const string PrivateToolDeploymentV2 = "chummer.build_ghost.private_tool_deployment.v2";
    public const string PrivateToolBodyCredentialEvidenceV1 = "chummer.build_ghost.private_tool_body_credential_evidence.v1";
    public const string CascadePrivateVoiceBindingV1 = "chummer.build_ghost.cascade_private_voice_binding.v1";
    public const string CartesiaPrivateVoiceReadReceiptV1 = "chummer.build_ghost.cartesia_private_voice_read_receipt.v1";
    public const string CartesiaScenarioSchemaReceiptV1 = "chummer.tough_tongue.cartesia_scenario_schema_receipt.v1";
    public const string PremiumLiveAvatarSchemaReceiptV1 = "chummer.tough_tongue.premium_live_avatar_schema_receipt.v1";
    public const string PremiumLiveAvatarBindingV1 = "chummer.tough_tongue.premium_live_avatar_binding.v1";
    public const string CustomFunctionLibrarySchemaReceiptV1 = "chummer.tough_tongue.custom_function_library_schema_receipt.v1";
    public const string CustomFunctionLibraryReadReceiptV1 = "chummer.tough_tongue.custom_function_library_read_receipt.v1";
    public const string CustomFunctionLibraryReadReceiptV2 = "chummer.tough_tongue.custom_function_library_read_receipt.v2";
    public const string CustomFunctionDynamicAuthorizationReceiptV1 = "chummer.tough_tongue.custom_function_dynamic_authorization_receipt.v1";
    public const string CustomFunctionDefinitionV1 = "chummer.tough_tongue.custom_function_definition.v1";
    public const string CustomFunctionDefinitionV2 = "chummer.tough_tongue.custom_function_definition.v2";
    public const string CustomFunctionBindingV1 = "chummer.tough_tongue.custom_function_binding.v1";
    public const string CustomFunctionBindingV2 = "chummer.tough_tongue.custom_function_binding.v2";
    public const string CustomFunctionAttachmentReceiptV1 = "chummer.tough_tongue.custom_function_attachment_receipt.v1";
    public const string ScenarioCanaryReceiptV1 = "chummer.tough_tongue.build_ghost_canary_receipt.v1";
    public const string CartesiaVoiceDeletionReceiptV1 = "chummer.build_ghost.cartesia_voice_deletion_receipt.v1";
    public const string ScenarioDeletionBlockerReceiptV1 = "chummer.tough_tongue.scenario_deletion_blocker_receipt.v1";
}

public static class ToughTongueBuildGhostPersonaIds
{
    public const string Rook = "build-ghost-rook-v1";
    public const string StockDefaultAvatar = "build-ghost-tough-tongue-stock-avatar-v1";
    public const string RookVoice = "build-ghost-rook-voice-v1";
}

public static class ToughTongueBuildGhostStockAvatarSelections
{
    public const string ProviderNamespace = "avatario";
    public const string ProviderStock = "provider-stock";
    public const string SelectedAvatarName = "Amelia";
    public const string SelectedAvatarAssetPath = "/live-avatars/avatars/Amelia.jpg";
    public const string RequiredModelProvider = "Landmass";
    public const string CurrentModelId = "gemini";
    public const string LegacyModelId = "cascade";
}

public static class ToughTongueBuildGhostVoiceProviders
{
    public const string CartesiaNamespace = "cartesia";
    public const string CartesiaTtsProvider = "Cartesia";
    public const string FullySyntheticProvenance = "fully-synthetic-no-human-recording";
}

public static class ToughTongueBuildGhostLiveAvatarProviders
{
    public const string Anam = "anam";
    public const string Avatario = "avatario";
    public const string HeyGen = "liveavatar";
    public const string RequiredModelProvider = "Landmass";
    public const decimal PremiumMinutesMultiplier = 2m;
}

public sealed record ToughTongueBuildGhostRequest(
    string Schema,
    string RequestId,
    string OwnerScopeHash,
    string PacketDigest,
    string Locale,
    string AnalysisPacketJson,
    string DeterministicFallbackText,
    string IdempotencyKey,
    DateTimeOffset RequestedAtUtc);

public sealed record ToughTongueBuildGhostProviderAnswer(
    string Schema,
    string RequestId,
    string PacketDigest,
    string Locale,
    string Text,
    IReadOnlyList<string> ReferencedFactIds,
    IReadOnlyList<string> ReferencedStrategyIds,
    IReadOnlyList<string> ReferencedRuleExplanationIds,
    IReadOnlyList<string> ReferencedVariantIds,
    IReadOnlyList<string> ReferencedMemberRefs,
    IReadOnlyList<string> ReferencedSourceAnchorIds,
    IReadOnlyList<string> SuggestedActionIds,
    IReadOnlyList<string> Links);

public sealed record ToughTongueBuildGhostReceipt(
    string Schema,
    string ReceiptId,
    string RequestId,
    string PacketDigest,
    string Locale,
    string IdempotencyDigest,
    string OutcomeStatus,
    string ProviderId,
    string ModelId,
    string AgentId,
    string VoiceId,
    bool RemoteExecutionEnabled,
    bool RemoteAttempted,
    string? AccountSlotId,
    string AccountSelectionPosture,
    string CircuitPosture,
    int ConfiguredSlotCount,
    int HealthySlotCount,
    long? InputTokens,
    long? OutputTokens,
    decimal? MinutesUsed,
    string? FallbackReason,
    IReadOnlyList<string> ValidationReasons,
    DateTimeOffset StartedAtUtc,
    DateTimeOffset CompletedAtUtc,
    long DurationMilliseconds);

public sealed record ToughTongueBuildGhostResult(
    string OutcomeStatus,
    string SafeText,
    bool UsedDeterministicFallback,
    ToughTongueBuildGhostProviderAnswer? ProviderAnswer,
    ToughTongueBuildGhostReceipt Receipt);

public sealed record ToughTongueBuildGhostTransportRequest(
    string Schema,
    string RequestId,
    string PacketDigest,
    string Locale,
    string AnalysisPacketJson,
    string IdempotencyKey);

public sealed record ToughTongueBuildGhostTransportResult(
    bool Success,
    string OutcomeCode,
    string? ResponseJson,
    bool QuotaExhausted = false,
    bool Retryable = false,
    long? InputTokens = null,
    long? OutputTokens = null,
    decimal? MinutesUsed = null);

public sealed record ToughTongueBuildGhostToolDefinition(
    string Schema,
    string Name,
    string Description,
    string HttpMethod,
    Uri Endpoint,
    IReadOnlyList<string> RequiredHeaderNames,
    string BodySchemaJson,
    int MaximumResponseCharacters,
    int TimeoutSeconds,
    string ContractDigest);

public sealed record BuildGhostPrivateToolDefinition(
    string Schema,
    string Name,
    string Description,
    string HttpMethod,
    Uri Endpoint,
    IReadOnlyList<string> RequiredHeaderNames,
    string BodySchemaJson,
    int MaximumResponseCharacters,
    int TimeoutSeconds,
    string ContractDigest);

public sealed record BuildGhostPrivateToolDeploymentPackage(
    string Schema,
    string DeploymentId,
    BuildGhostPrivateToolDefinition Tool,
    string AuthenticationScheme,
    string AuthenticationAudience,
    string ResponseSchema,
    int PacketAccessTtlSeconds,
    bool ProviderNeutral,
    bool RemoteExecutionEnabled,
    string ContractDigest);

public sealed record BuildGhostPrivateToolDeploymentValidation(
    bool Accepted,
    BuildGhostPrivateToolDeploymentPackage? Package,
    IReadOnlyList<string> RejectionReasons);

[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record BuildGhostPrivateToolRequest(
    [property: JsonPropertyName("packet_access_key")] string PacketAccessKey,
    [property: JsonPropertyName("packet_digest")] string PacketDigest,
    [property: JsonPropertyName("locale")] string Locale,
    [property: JsonPropertyName("request_kind")] string RequestKind,
    [property: JsonPropertyName("question")] string? Question);

[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record BuildGhostPrivateToolProviderRequest(
    [property: JsonPropertyName("schema")] string Schema,
    [property: JsonPropertyName("packet_access_key")] string PacketAccessKey,
    [property: JsonPropertyName("packet_digest")] string PacketDigest,
    [property: JsonPropertyName("locale")] string Locale,
    [property: JsonPropertyName("request_kind")] string RequestKind,
    [property: JsonPropertyName("question")] string? Question);

[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record BuildGhostPrivateToolAuthorityRequest(
    [property: JsonPropertyName("packet_access_key")] string PacketAccessKey,
    [property: JsonPropertyName("packet_digest")] string PacketDigest,
    [property: JsonPropertyName("locale")] string Locale,
    [property: JsonPropertyName("request_kind")] string RequestKind);

public sealed record BuildGhostCartesiaPrivateVoiceReadReceipt(
    string Schema,
    string ProviderNamespace,
    string RequestedVoiceId,
    string ReturnedVoiceId,
    int ReadHttpStatus,
    bool IsOwner,
    string Access,
    string Visibility,
    string SyntheticProvenance,
    string SourceVoiceReleaseDigest,
    string ProviderResponseDigest,
    DateTimeOffset ObservedAtUtc);

public sealed record BuildGhostToughTongueCartesiaScenarioSchemaReceipt(
    string Schema,
    string ProviderNamespace,
    string DeploymentId,
    Uri ScenarioReadBundleUrl,
    string ScenarioReadBundleDigest,
    long ScenarioReadBundleBytes,
    Uri ScenarioCreateBundleUrl,
    string ScenarioCreateBundleDigest,
    long ScenarioCreateBundleBytes,
    string CreateTtsProviderFieldPath,
    string CreateTtsVoiceIdFieldPath,
    string ReadTtsProviderFieldPath,
    string ReadTtsVoiceIdFieldPath,
    string TtsProvider,
    DateTimeOffset ObservedAtUtc);

public sealed record BuildGhostToughTonguePremiumLiveAvatarSchemaReceipt(
    string Schema,
    string ProviderNamespace,
    string DeploymentId,
    Uri StudioBundleUrl,
    string StudioBundleDigest,
    long StudioBundleBytes,
    Uri ScenarioRuntimeBundleUrl,
    string ScenarioRuntimeBundleDigest,
    long ScenarioRuntimeBundleBytes,
    Uri SessionCreateBundleUrl,
    string SessionCreateBundleDigest,
    long SessionCreateBundleBytes,
    string ScenarioLiveAvatarIdFieldPath,
    string ScenarioLiveAvatarProviderFieldPath,
    string RuntimeEnabledFieldPath,
    string RuntimeAvatarIdFieldPath,
    string RuntimeProviderFieldPath,
    string RequiredModelProvider,
    IReadOnlyList<string> AllowedProviders,
    decimal AnamMinutesMultiplier,
    decimal HeyGenMinutesMultiplier,
    bool ProviderManagedLipSynchronizationAdvertised,
    DateTimeOffset ObservedAtUtc);

public sealed record BuildGhostToughTonguePremiumLiveAvatarBinding(
    string Schema,
    string Provider,
    [property: JsonIgnore] string ProviderAvatarId,
    string ProviderAvatarIdDigest,
    string RequiredModelProvider,
    decimal MinutesMultiplier,
    bool ProviderManagedLipSynchronization,
    string SchemaReceiptDigest,
    string ContractDigest);

public sealed record BuildGhostToughTongueCustomFunctionLibrarySchemaReceipt(
    string Schema,
    string ProviderNamespace,
    string DeploymentId,
    string ServiceChunkName,
    string ServiceChunkDigest,
    long ServiceChunkBytes,
    string StudioChunkName,
    string StudioChunkDigest,
    long StudioChunkBytes,
    string ScenarioServiceChunkName,
    string ScenarioServiceChunkDigest,
    long ScenarioServiceChunkBytes,
    string RuntimeChunkName,
    string RuntimeChunkDigest,
    long RuntimeChunkBytes,
    Uri ApiBaseUri,
    string ListPath,
    string ByScenarioPathTemplate,
    string CreatePath,
    string UpdatePathTemplate,
    string ExecutePathTemplate,
    string DeletePathTemplate,
    string ScenarioUpsertPath,
    IReadOnlyList<string> CreateFields,
    IReadOnlyList<string> ReturnedFields,
    string ScenarioAttachmentField,
    string RuntimeRegistrationPrefix,
    DateTimeOffset ObservedAtUtc);

public sealed record BuildGhostToughTongueCustomFunctionLibraryReadReceipt(
    string Schema,
    Uri Endpoint,
    string Method,
    string SelectedSlotLabel,
    string AccountRefDigest,
    int HttpStatus,
    string JsonResponseShape,
    int RowCount,
    bool JsonSchemaObserved,
    IReadOnlyList<string> ReturnedFields,
    string ProviderResponseDigest,
    bool RawResponseExposed,
    bool RawIdsExposed,
    bool CredentialExposed,
    DateTimeOffset ObservedAtUtc);

public sealed record BuildGhostToughTongueDynamicAuthorizationReceipt(
    string Schema,
    string ProviderNamespace,
    string DeploymentId,
    string EvidenceSource,
    string EvidenceDigest,
    string HeaderName,
    string HeaderValueTemplate,
    string ArgumentName,
    string InterpolationSemantics,
    bool StoredHeaderValuesInterpolateToolArguments,
    DateTimeOffset ObservedAtUtc);

public sealed record BuildGhostToughTongueCustomFunctionDefinition(
    string Schema,
    JsonObject Payload,
    string ToolContractDigest,
    string ToolDeploymentDigest,
    string LibrarySchemaReceiptDigest,
    string LibraryReadReceiptDigest,
    string DynamicAuthorizationReceiptDigest,
    bool LibrarySchemaVerified,
    bool AuthenticatedLibraryReadVerified,
    bool DynamicAuthorizationVerified,
    string AuthenticationMode,
    string AuthenticationEvidenceDigest,
    bool AuthenticationVerified,
    IReadOnlyList<string> BlockingReasons,
    string ContractDigest);

public sealed record BuildGhostToughTongueCustomFunctionBinding(
    string Schema,
    [property: JsonIgnore] string ProviderCustomFunctionId,
    string ProviderCustomFunctionIdDigest,
    string DefinitionContractDigest,
    string ToolContractDigest,
    string ToolDeploymentDigest,
    string LibrarySchemaReceiptDigest,
    string LibraryReadReceiptDigest,
    string DynamicAuthorizationReceiptDigest,
    string AuthenticationMode,
    string AuthenticationEvidenceDigest,
    bool AuthenticationVerified,
    int StoredReadHttpStatus,
    bool StoredFieldsExactMatch,
    string StoredResponseDigest,
    bool RawResponseExposed,
    bool RawIdsExposed,
    bool CredentialExposed,
    DateTimeOffset ObservedAtUtc,
    string ContractDigest);

public sealed record BuildGhostToughTongueCustomFunctionAttachmentReceipt(
    string Schema,
    string ScenarioIdDigest,
    string ProviderCustomFunctionIdDigest,
    string DefinitionContractDigest,
    string BindingContractDigest,
    string ScenarioAttachmentField,
    int ScenarioReadHttpStatus,
    bool ScenarioAttachmentExactMatch,
    int ByScenarioReadHttpStatus,
    bool ByScenarioAttachmentExactMatch,
    bool RawResponseExposed,
    bool RawIdsExposed,
    bool CredentialExposed,
    IReadOnlyList<string> BlockingReasons,
    DateTimeOffset ObservedAtUtc,
    string ContractDigest);

public sealed record BuildGhostCascadePrivateVoiceBinding(
    string Schema,
    string ModelProvider,
    string ModelId,
    string TtsProvider,
    string ProviderNamespace,
    string VoiceAlias,
    string ProviderVoiceRef,
    string VoiceReleaseDigest,
    string VoiceReadReceiptDigest,
    IReadOnlyList<string> SupportedLocales,
    string ContractDigest);

public sealed record BuildGhostToughTongueStockAvatarBinding(
    string Schema,
    string ProviderNamespace,
    string AvatarAlias,
    string SelectionMode,
    string AvatarName,
    string AvatarAssetPath,
    [property: JsonIgnore] string ProviderAvatarId,
    string ProviderAvatarIdDigest,
    string ModelProvider,
    string ModelId,
    bool LegacyModelCompatibilityEnabled,
    string ProviderReadbackDigest,
    string ProviderCanonicalResponseDigest,
    string ProviderReadbackScenarioRefDigest,
    string ProviderReadbackSource,
    string ProviderReadbackObservedAtUtc,
    int ProviderReadbackMaximumAgeSeconds,
    bool ProviderReadVerified,
    string ContractDigest);

public sealed record BuildGhostToughTongueStockAvatarReadbackReceipt(
    string Schema,
    int HttpStatus,
    string CanonicalWhitelistedResponseDigest,
    string ObservedProvider,
    string ObservedAvatarName,
    string ObservedAvatarAssetPath,
    string ObservedLiveAvatarId,
    string ObservedModelProvider,
    string ObservedModelId,
    bool LegacyCascadePolicyOptIn,
    string ScenarioRefDigest,
    string Source,
    string ObservedAtUtc,
    int MaximumAgeSeconds,
    string ReceiptDigest);

public sealed record BuildGhostToughTongueStockAvatarBindingValidation(
    bool Accepted,
    BuildGhostToughTongueStockAvatarBinding? Binding,
    IReadOnlyList<string> RejectionReasons);

public sealed record ToughTongueBuildGhostScenarioCandidate(
    string Schema,
    JsonObject Payload,
    BuildGhostPrivateToolDefinition Tool,
    IReadOnlyList<string> SupportedLocales,
    string? TtsProviderFieldPath,
    string? TtsVoiceIdFieldPath,
    bool ProviderSchemaReadVerified,
    BuildGhostToughTongueCustomFunctionBinding? CustomFunctionBinding,
    string CustomFunctionBindingDigest,
    bool CustomFunctionBindingReadVerified,
    IReadOnlyList<string> BlockingReasons,
    string ContractDigest,
    BuildGhostToughTonguePremiumLiveAvatarBinding? LiveAvatarBinding = null,
    string LiveAvatarBindingDigest = "",
    bool LiveAvatarSchemaVerified = false,
    string? LiveAvatarIdFieldPath = null,
    string? LiveAvatarProviderFieldPath = null,
    BuildGhostToughTongueStockAvatarBinding? StockAvatarBinding = null);

public sealed record ToughTongueBuildGhostScenarioValidation(
    bool Accepted,
    string? ScenarioId,
    IReadOnlyList<string> RejectionReasons);

public sealed record ToughTongueBuildGhostScenarioAccessGrant(
    string ScenarioId,
    string AccessToken,
    DateTimeOffset ExpiresAtUtc);

public sealed record ToughTongueBuildGhostCanaryReceipt(
    string Schema,
    string OutcomeStatus,
    string ScenarioIdDigest,
    string ScenarioContractDigest,
    string ToolDeploymentDigest,
    string RuntimeBindingDigest,
    bool RemoteExecutionEnabled,
    bool ReadOnlyScenarioCheckEnabled,
    bool ScenarioReadAttempted,
    bool ScenarioAccepted,
    bool AccessGrantEnabled,
    bool AccessGrantAttempted,
    bool AccessGrantCreated,
    DateTimeOffset? AccessGrantExpiresAtUtc,
    IReadOnlyList<string> BlockingReasons,
    DateTimeOffset ObservedAtUtc);

public sealed record BuildGhostCartesiaVoiceDeletionReceipt(
    string Schema,
    string OutcomeStatus,
    string VoiceIdDigest,
    bool DeleteAttempted,
    int? DeleteHttpStatus,
    bool ReadbackAttempted,
    int? ReadbackHttpStatus,
    bool OwnerListAttempted,
    int? OwnerListHttpStatus,
    bool OwnerListAbsenceVerified,
    bool RawResponseExposed,
    bool RawVoiceIdExposed,
    bool CredentialExposed,
    IReadOnlyList<string> BlockingReasons,
    DateTimeOffset ObservedAtUtc);

public sealed record ToughTongueBuildGhostScenarioDeletionBlockerReceipt(
    string Schema,
    string OutcomeStatus,
    string ScenarioIdDigest,
    bool TransportAttempted,
    IReadOnlyList<string> BlockingReasons,
    DateTimeOffset ObservedAtUtc);

public sealed record BuildGhostPersonaMediaRelease(
    string Schema,
    string ReleaseId,
    string PersonaId,
    string AssetId,
    string AssetKind,
    string Owner,
    string Provenance,
    string ContentDigest,
    string ConsentReceiptId,
    string LicensePosture,
    string ProviderVerificationState,
    string ReleaseState,
    DateTimeOffset ReviewedAtUtc);

public sealed record BuildGhostPersonaReleaseProjection(
    string PersonaId,
    string AvatarId,
    string VoiceId,
    string AvatarReleaseState,
    string VoiceReleaseState,
    bool AvatarReady,
    bool VoiceReady,
    string FallbackPosture,
    IReadOnlyList<string> BlockingReasons);
