using System.Text.Json.Nodes;

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
}

public static class ToughTongueBuildGhostPersonaIds
{
    public const string Rook = "build-ghost-rook-v1";
    public const string RookAvatar = "build-ghost-rook-avatar-v1";
    public const string RookVoice = "build-ghost-rook-voice-v1";
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

public sealed record ToughTongueBuildGhostScenarioCandidate(
    string Schema,
    JsonObject Payload,
    ToughTongueBuildGhostToolDefinition Tool,
    IReadOnlyList<string> SupportedLocales,
    string ContractDigest);

public sealed record ToughTongueBuildGhostScenarioValidation(
    bool Accepted,
    string? ScenarioId,
    IReadOnlyList<string> RejectionReasons);

public sealed record ToughTongueBuildGhostScenarioAccessGrant(
    string ScenarioId,
    string AccessToken,
    DateTimeOffset ExpiresAtUtc);

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
