using System.Text.Json.Nodes;
using System.Text.Json.Serialization;
using System.Security.Cryptography;
using System.Text;

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
    public const string ReadOnlyBindingContractV3 = "chummer.build_ghost.tough_tongue.read_only_binding_contract.v3";
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
    public const string SupportExperienceV1 = "chummer.build_ghost.support_experience.v1";
    public const string LiveSupportRequestV1 = "chummer.build_ghost.live_support_request.v1";
    public const string LiveSupportSessionV1 = "chummer.build_ghost.live_support_session.v1";
    public const string LiveSupportCapabilityReceiptV1 = "chummer.build_ghost.live_support_capability_receipt.v1";
    public const string LiveSupportStatusRequestV1 = "chummer.build_ghost.live_support_status_request.v1";
}

public static class ToughTongueBuildGhostPersonaIds
{
    public const string Rook = "build-ghost-rook-v1";
    public const string RookAvatar = "build-ghost-rook-avatar-v1";
    public const string RookVidBoardSupport = "build-ghost-rook-vidboard-support-v1";
    public const string StockDefaultAvatar = "build-ghost-tough-tongue-stock-avatar-v1";
    public const string RookVoice = "build-ghost-rook-voice-v1";
}

public static class BuildGhostSupportChannelKinds
{
    public const string RookVidBoard = "rook_vidboard";
    public const string LivePhotorealMeeting = "live_photoreal_meeting";
}

public static class BuildGhostLiveMeetingProviders
{
    public const string Zoom = "zoom";
    public const string Teams = "teams";
}

public static class BuildGhostLiveSupportStatuses
{
    public const string Unavailable = "unavailable";
    public const string Requested = "requested";
    public const string ProvisioningMeeting = "provisioning_meeting";
    public const string ProvisioningAvatar = "provisioning_avatar";
    public const string Ready = "ready";
    public const string Active = "active";
    public const string Completed = "completed";
    public const string Failed = "failed";
    public const string Cancelled = "cancelled";
    public const string Expired = "expired";
}

public static class BuildGhostLiveSupportDisclosureContract
{
    public const string CurrentVersion = "chummer.build_ghost.live_support_disclosure.v1";
    public const string RecordingDisclosure =
        "The live-support meeting may be recorded or transcribed and the meeting must disclose this before it starts.";
    public const string ExternalProviderProcessingDisclosure =
        "The selected meeting provider and Tough Tongue may process the meeting data needed for live support.";

    public static string ComputeDigest()
    {
        string authority = string.Join(
            '\n',
            CurrentVersion,
            RecordingDisclosure,
            ExternalProviderProcessingDisclosure);
        return $"sha256:{Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(authority))).ToLowerInvariant()}";
    }
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
    string OperatorReadOnlyContractDigest,
    string OperatorReadOnlyContractFileDigest,
    string ProviderReadbackReceiptFileDigest,
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

public sealed record BuildGhostDefaultSupportProjection(
    string ChannelKind,
    string PersonaId,
    string AvatarId,
    string MediaAssetId,
    string? PreRenderedVideoHref,
    string MediaContentDigest,
    bool PreRenderedVideoReady,
    string AvailabilityStatus,
    string DeterministicTextFallback,
    IReadOnlyList<string> BlockingReasons);

public sealed record BuildGhostLiveSupportCapabilityProjection(
    string ChannelKind,
    bool RequestAvailable,
    IReadOnlyList<string> MeetingProviders,
    string AvatarPresentation,
    bool RecordingDisclosureRequired,
    IReadOnlyList<string> BlockingReasons);

public sealed record BuildGhostSupportExperienceProjection(
    string Schema,
    BuildGhostDefaultSupportProjection DefaultSupport,
    BuildGhostLiveSupportCapabilityProjection LiveSupport);

[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record BuildGhostLiveSupportRequest(
    [property: JsonPropertyName("schema")] string Schema,
    [property: JsonPropertyName("request_id")] string RequestId,
    [property: JsonPropertyName("owner_scope_hash")] string OwnerScopeHash,
    [property: JsonPropertyName("workspace_id")] string WorkspaceId,
    [property: JsonPropertyName("workspace_revision")] long WorkspaceRevision,
    [property: JsonPropertyName("source_digest")] string SourceDigest,
    [property: JsonPropertyName("locale")] string Locale,
    [property: JsonPropertyName("meeting_provider")] string MeetingProvider,
    [property: JsonPropertyName("recording_consent_granted")] bool RecordingConsentGranted,
    [property: JsonPropertyName("external_provider_processing_consent_granted")] bool ExternalProviderProcessingConsentGranted,
    [property: JsonPropertyName("disclosure_version")] string DisclosureVersion,
    [property: JsonPropertyName("disclosure_digest")] string DisclosureDigest,
    [property: JsonPropertyName("requested_duration_minutes")] int RequestedDurationMinutes,
    [property: JsonPropertyName("idempotency_key")] string IdempotencyKey,
    [property: JsonPropertyName("requested_at_utc")] DateTimeOffset RequestedAtUtc);

[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record BuildGhostLiveSupportStatusRequest(
    [property: JsonPropertyName("schema")] string Schema,
    [property: JsonPropertyName("owner_scope_hash")] string OwnerScopeHash,
    [property: JsonPropertyName("request_id")] string RequestId,
    [property: JsonPropertyName("workspace_id")] string WorkspaceId,
    [property: JsonPropertyName("source_digest")] string SourceDigest);

public sealed record BuildGhostLiveSupportCapabilityReceipt(
    string Schema,
    IReadOnlyList<string> MeetingProviders,
    string AccountScopeRefDigest,
    string ScenarioRefDigest,
    string AvatarAlias,
    string AvatarBindingDigest,
    bool PhotorealisticVideoInMeetingVerified,
    bool RecordingDisclosureRequired,
    decimal AvailableMinutesAtObservation,
    decimal ReservedMinutes,
    decimal LiveAvatarMinutesMultiplier,
    string EvidenceSource,
    DateTimeOffset ObservedAtUtc,
    int MaximumAgeSeconds,
    string ReceiptDigest,
    string AuthorityMac);

public sealed record BuildGhostMeetingLinkProvisioningCommand(
    string RequestId,
    string OwnerScopeHash,
    string MeetingProvider,
    string Locale,
    int DurationMinutes,
    string IdempotencyKey);

public sealed record BuildGhostMeetingLinkProvisioningResult(
    bool Success,
    bool ReconciliationRequired,
    string OutcomeCode,
    string MeetingProvider,
    Uri? JoinUrl,
    [property: JsonIgnore] string CancellationHandle,
    string ProviderMeetingRefDigest,
    string ProviderResponseDigest,
    DateTimeOffset? StartsAtUtc,
    DateTimeOffset? ExpiresAtUtc);

public sealed record BuildGhostMeetingLinkCancellationCommand(
    string RequestId,
    string MeetingProvider,
    string CancellationHandle,
    string IdempotencyKey);

public sealed record BuildGhostMeetingLinkCancellationResult(
    bool Success,
    string OutcomeCode,
    string ProviderResponseDigest);

public sealed record BuildGhostToughTongueMeetingBotCommand(
    string RequestId,
    string MeetingProvider,
    Uri JoinUrl,
    string IdempotencyKey);

public sealed record BuildGhostToughTongueMeetingBotResult(
    bool Success,
    bool ReconciliationRequired,
    string OutcomeCode,
    string BotRefDigest,
    string SessionRefDigest,
    string ProviderResponseDigest);

public sealed record BuildGhostLiveSupportSessionProjection(
    string Schema,
    string RequestId,
    string ChannelKind,
    string Status,
    string MeetingProvider,
    Uri? JoinUrl,
    DateTimeOffset? JoinUrlExpiresAtUtc,
    string AvatarAlias,
    string AvatarPresentation,
    bool RecordingConsentGranted,
    bool ExternalProviderProcessingConsentGranted,
    string DisclosureVersion,
    string DisclosureDigest,
    string MeetingLinkDigest,
    string MeetingReceiptDigest,
    string MeetingBotReceiptDigest,
    string CapabilityReceiptDigest,
    DateTimeOffset RequestedAtUtc,
    DateTimeOffset UpdatedAtUtc,
    BuildGhostDefaultSupportProjection FallbackSupport,
    IReadOnlyList<string> BlockingReasons);
