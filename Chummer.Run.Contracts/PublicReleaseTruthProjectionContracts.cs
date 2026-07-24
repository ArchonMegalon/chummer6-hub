using System.Text.Json.Serialization;

namespace Chummer.Run.Contracts.PublicSurface;

public sealed record PublicPreviewByteHandoffDto(
    [property: JsonPropertyName("contractName")] string ContractName,
    [property: JsonPropertyName("status")] string Status,
    [property: JsonPropertyName("sourcePublicationState")] string SourcePublicationState,
    [property: JsonPropertyName("releaseScopeDecisionSha256")] string ReleaseScopeDecisionSha256,
    [property: JsonPropertyName("releaseVersion")] string ReleaseVersion,
    [property: JsonPropertyName("channel")] string Channel,
    [property: JsonPropertyName("artifactId")] string ArtifactId,
    [property: JsonPropertyName("head")] string Head,
    [property: JsonPropertyName("platform")] string Platform,
    [property: JsonPropertyName("rid")] string Rid,
    [property: JsonPropertyName("arch")] string Arch,
    [property: JsonPropertyName("sha256")] string Sha256,
    [property: JsonPropertyName("sizeBytes")] long SizeBytes,
    [property: JsonPropertyName("artifactAccessClass")] string ArtifactAccessClass,
    [property: JsonPropertyName("signingRequirement")] string SigningRequirement,
    [property: JsonPropertyName("downloadUrl")] string DownloadUrl,
    [property: JsonPropertyName("publicInstallRoute")] string PublicInstallRoute);

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

    [JsonPropertyName("releaseScopeDecisionSha256")]
    public string ReleaseScopeDecisionSha256 { get; init; } = Missing;

    [JsonPropertyName("artifactHandoff")]
    public PublicPreviewByteHandoffDto? ArtifactHandoff { get; init; }

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
    public bool ReviewRequiredPublicByteHandoffsAllowed =>
        AuthorityBound
        && ProjectionShapeValid
        && IsSha256(ReleaseScopeDecisionSha256)
        && string.Equals(ReleaseDecisionStatus, "review_required", StringComparison.Ordinal)
        && string.Equals(Channel, "preview", StringComparison.Ordinal)
        && string.Equals(ReleaseStatus, "published", StringComparison.Ordinal)
        && string.Equals(RolloutState, "public_release_review_required", StringComparison.Ordinal)
        && string.Equals(SupportabilityState, "review_required", StringComparison.Ordinal)
        && ArtifactCount == 1
        && AvailablePlatforms.SequenceEqual(["windows"], StringComparer.Ordinal)
        && PrimaryHeadByPlatform.Count == 1
        && PrimaryHeadByPlatform.TryGetValue("windows", out string? primaryHead)
        && string.Equals(primaryHead, "avalonia", StringComparison.Ordinal)
        && string.Equals(DownloadAccessPosture, "open_public", StringComparison.Ordinal)
        && ArtifactHandoff is
        {
            ContractName: "chummer.public-preview-byte-handoff/v1",
            Status: "approved_public_preview_bytes",
            SourcePublicationState: "preview",
            Channel: "preview",
            Head: "avalonia",
            Platform: "windows",
            Rid: "win-x64",
            Arch: "x64",
            ArtifactAccessClass: "open_public",
            SigningRequirement: "preview_unsigned_allowed",
            SizeBytes: > 0
        } handoff
        && string.Equals(
            handoff.ReleaseScopeDecisionSha256,
            ReleaseScopeDecisionSha256,
            StringComparison.Ordinal)
        && string.Equals(handoff.ReleaseVersion, ReleaseVersion, StringComparison.Ordinal)
        && IsSha256(handoff.Sha256)
        && IsSafeDecodedRouteSegment(handoff.ArtifactId)
        && IsCanonicalPublicPreviewDownloadUrl(handoff.DownloadUrl)
        && string.Equals(
            handoff.PublicInstallRoute,
            $"/downloads/install/{handoff.ArtifactId}",
            StringComparison.Ordinal)
        && !string.Equals(
            handoff.DownloadUrl,
            handoff.PublicInstallRoute,
            StringComparison.Ordinal);

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

    private static bool IsCanonicalPublicPreviewDownloadUrl(string value)
    {
        const string prefix = "/downloads/g/";
        if (!value.StartsWith(prefix, StringComparison.Ordinal)
            || value.Contains('?')
            || value.Contains('#')
            || value.Contains('\\')
            || value.Any(static character => char.IsWhiteSpace(character) || char.IsControl(character)))
        {
            return false;
        }

        string remainder = value[prefix.Length..];
        int generationSeparator = remainder.IndexOf('/');
        if (generationSeparator <= 0
            || !IsSafeDecodedRouteSegment(remainder[..generationSeparator]))
        {
            return false;
        }

        const string filesPrefix = "/files/";
        string fileRoute = remainder[generationSeparator..];
        return fileRoute.StartsWith(filesPrefix, StringComparison.Ordinal)
            && IsSafeDecodedRouteSegment(fileRoute[filesPrefix.Length..]);
    }

    private static bool IsSafeDecodedRouteSegment(string value)
    {
        if (value.Length == 0
            || value.Contains('/')
            || value.Contains('\\')
            || value.Any(static character => char.IsWhiteSpace(character) || char.IsControl(character)))
        {
            return false;
        }

        try
        {
            string decoded = Uri.UnescapeDataString(value);
            return decoded is not "." and not ".."
                && !decoded.Contains('/')
                && !decoded.Contains('\\')
                && !decoded.Any(static character =>
                    char.IsWhiteSpace(character) || char.IsControl(character));
        }
        catch (UriFormatException)
        {
            return false;
        }
    }

    private static bool IsGitCommit(string value)
        => value.Length == 40 && value.All(static character =>
            character is >= '0' and <= '9' or >= 'a' and <= 'f');
}
