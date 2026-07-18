using System.Text.Json.Serialization;

namespace Chummer.Run.Contracts.PublicSurface;

public sealed record PublicReleaseTruthProjectionDto(
    [property: JsonPropertyName("contractName")] string ContractName,
    [property: JsonPropertyName("releaseVersion")] string ReleaseVersion,
    [property: JsonPropertyName("channel")] string Channel,
    [property: JsonPropertyName("releaseStatus")] string ReleaseStatus,
    [property: JsonPropertyName("rolloutState")] string RolloutState,
    [property: JsonPropertyName("supportabilityState")] string SupportabilityState,
    [property: JsonPropertyName("availablePlatforms")] IReadOnlyList<string> AvailablePlatforms,
    [property: JsonPropertyName("primaryHeadByPlatform")] IReadOnlyDictionary<string, string> PrimaryHeadByPlatform,
    [property: JsonPropertyName("artifactCount")] int ArtifactCount,
    [property: JsonPropertyName("downloadAccessPosture")] string DownloadAccessPosture,
    [property: JsonPropertyName("knownIssueSummary")] string KnownIssueSummary,
    [property: JsonPropertyName("manifestSha256")] string ManifestSha256,
    [property: JsonPropertyName("registryCommit")] string RegistryCommit,
    [property: JsonPropertyName("releaseDecisionStatus")] string ReleaseDecisionStatus,
    [property: JsonPropertyName("releaseDecisionSha256")] string ReleaseDecisionSha256)
{
    public const string Schema = "chummer.release-truth-projection/v1";
    public const string Missing = "missing";
    public const string Unknown = "unknown";
    public const string Invalid = "invalid";

    [JsonIgnore]
    public bool AuthorityBound =>
        IsSha256(ManifestSha256)
        && IsGitCommit(RegistryCommit)
        && IsSha256(ReleaseDecisionSha256)
        && ReleaseDecisionStatus is "review_required" or "preview_ready" or "stable_ready";

    [JsonIgnore]
    public bool AvailabilityClaimsAllowed =>
        AuthorityBound
        && ProjectionShapeValid
        && ReleaseDecisionStatus is "preview_ready" or "stable_ready"
        && string.Equals(ReleaseStatus, "published", StringComparison.Ordinal)
        && ArtifactCount > 0
        && AvailablePlatforms.Count > 0
        && DownloadAccessPosture is "open_public" or "account_recommended" or "account_required" or "mixed"
        && !IsBlockingRolloutState(RolloutState)
        && !IsBlockingSupportabilityState(SupportabilityState);

    [JsonIgnore]
    public bool StableClaimsAllowed =>
        AvailabilityClaimsAllowed
        && string.Equals(ReleaseDecisionStatus, "stable_ready", StringComparison.Ordinal)
        && (string.Equals(Channel, "stable", StringComparison.Ordinal)
            || string.Equals(Channel, "public_stable", StringComparison.Ordinal))
        && string.Equals(RolloutState, "public_stable", StringComparison.Ordinal)
        && string.Equals(SupportabilityState, "gold_supported", StringComparison.Ordinal);

    [JsonIgnore]
    public bool ReviewBannerRequired =>
        !AuthorityBound
        || !ProjectionShapeValid
        || string.Equals(ReleaseDecisionStatus, "review_required", StringComparison.Ordinal)
        || IsBlockingRolloutState(RolloutState)
        || IsBlockingSupportabilityState(SupportabilityState);

    private static bool IsBlockingRolloutState(string value)
        => value is Missing or Unknown or Invalid
           || value.Contains("review", StringComparison.Ordinal)
           || value.Contains("revoked", StringComparison.Ordinal)
           || value.Contains("blocked", StringComparison.Ordinal)
           || value.Contains("withdrawn", StringComparison.Ordinal)
           || value.Contains("unpublished", StringComparison.Ordinal)
           || value.Contains("coverage_incomplete", StringComparison.Ordinal);

    private static bool IsBlockingSupportabilityState(string value)
        => value is Missing or Unknown or Invalid
           || value.Contains("review", StringComparison.Ordinal)
           || value.Contains("unsupported", StringComparison.Ordinal)
           || value.Contains("unavailable", StringComparison.Ordinal)
           || value.Contains("blocked", StringComparison.Ordinal);

    private bool ProjectionShapeValid =>
        ReleaseVersion is not Missing and not Unknown and not Invalid
        && Channel is not Missing and not Unknown and not Invalid
        && ReleaseStatus is not Missing and not Unknown and not Invalid
        && KnownIssueSummary is not Invalid
        && ArtifactCount >= 0
        && !AvailablePlatforms.Any(static platform =>
            platform is Missing or Unknown or Invalid)
        && PrimaryHeadByPlatform.Count == AvailablePlatforms.Count
        && AvailablePlatforms.All(platform =>
            PrimaryHeadByPlatform.TryGetValue(platform, out string? head)
            && head is not Unknown and not Missing and not Invalid)
        && (ArtifactCount == 0
            ? AvailablePlatforms.Count == 0
              && PrimaryHeadByPlatform.Count == 0
              && DownloadAccessPosture == "unavailable"
              && ReleaseDecisionStatus == "review_required"
            : AvailablePlatforms.Count > 0
              && DownloadAccessPosture is "open_public" or "account_recommended" or "account_required" or "mixed");

    private static bool IsSha256(string value)
        => value.Length == 64 && value.All(static character =>
            character is >= '0' and <= '9' or >= 'a' and <= 'f');

    private static bool IsGitCommit(string value)
        => value.Length == 40 && value.All(static character =>
            character is >= '0' and <= '9' or >= 'a' and <= 'f');
}
