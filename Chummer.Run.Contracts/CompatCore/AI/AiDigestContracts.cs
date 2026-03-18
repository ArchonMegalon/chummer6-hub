using Chummer.Contracts.Characters;

namespace Chummer.Contracts.AI;

public static class AiDigestApiOperations
{
    public const string GetRuntimeSummary = "get-runtime-summary";
    public const string GetCharacterDigest = "get-character-digest";
    public const string GetSessionDigest = "get-session-digest";
}

public sealed record AiRuntimeSummaryProjection(
    string RuntimeFingerprint,
    string RulesetId,
    string Title,
    string CatalogKind,
    string EngineApiVersion,
    IReadOnlyList<string> ContentBundles,
    IReadOnlyList<string> RulePacks,
    IReadOnlyDictionary<string, string> ProviderBindings,
    string? Visibility = null,
    string? Description = null);

public sealed record AiCharacterDigestProjection(
    string CharacterId,
    string DisplayName,
    string RulesetId,
    string RuntimeFingerprint,
    CharacterFileSummary Summary,
    DateTimeOffset LastUpdatedUtc,
    bool HasSavedWorkspace = false);

public sealed record AiSessionDigestProjection(
    string CharacterId,
    string DisplayName,
    string RulesetId,
    string RuntimeFingerprint,
    string SelectionState,
    bool SessionReady,
    string BundleFreshness,
    bool RequiresBundleRefresh = false,
    string? ProfileId = null,
    string? ProfileTitle = null,
    string? DeferredReason = null);
