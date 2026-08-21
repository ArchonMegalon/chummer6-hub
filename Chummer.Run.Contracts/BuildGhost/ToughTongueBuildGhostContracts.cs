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
    public const string ScenarioContractV1 = "chummer.tough_tongue.build_ghost_scenario.v1";
    public const string ToolContractV1 = "chummer.tough_tongue.build_ghost_tool.v1";
    public const string PrivateToolContractV1 = "chummer.build_ghost.private_tool.v1";
    public const string PrivateToolDeploymentV1 = "chummer.build_ghost.private_tool_deployment.v1";
    public const string CascadePrivateVoiceBindingV1 = "chummer.build_ghost.cascade_private_voice_binding.v1";
    public const string CartesiaPrivateVoiceReadReceiptV1 = "chummer.build_ghost.cartesia_private_voice_read_receipt.v1";
    public const string CartesiaScenarioFieldReceiptV1 = "chummer.tough_tongue.cartesia_scenario_field_receipt.v1";
    public const string ScenarioCanaryReceiptV1 = "chummer.tough_tongue.build_ghost_canary_receipt.v1";
}

public static class ToughTongueBuildGhostPersonaIds
{
    public const string Rook = "build-ghost-rook-v1";
    public const string RookAvatar = "build-ghost-rook-avatar-v1";
    public const string RookVoice = "build-ghost-rook-voice-v1";
}

public static class ToughTongueBuildGhostVoiceProviders
{
    public const string CartesiaNamespace = "cartesia";
    public const string CartesiaTtsProvider = "Cartesia";
    public const string FullySyntheticProvenance = "fully-synthetic-no-human-recording";
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

public sealed record BuildGhostToughTongueCartesiaScenarioFieldReceipt(
    string Schema,
    string ProviderNamespace,
    string TtsProvider,
    string ConfiguredFieldPath,
    string ReturnedFieldPath,
    string ReturnedValue,
    int ReadHttpStatus,
    string ProviderSchemaDigest,
    string ProviderResponseDigest,
    DateTimeOffset ObservedAtUtc);

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

public sealed record ToughTongueBuildGhostScenarioCandidate(
    string Schema,
    JsonObject Payload,
    BuildGhostPrivateToolDefinition Tool,
    IReadOnlyList<string> SupportedLocales,
    string? TtsProviderFieldPath,
    bool ProviderSchemaReadVerified,
    IReadOnlyList<string> BlockingReasons,
    string ContractDigest);

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
