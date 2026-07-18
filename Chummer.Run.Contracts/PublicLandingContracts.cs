using System.Text.Json;
using System.Text.Json.Serialization;

namespace Chummer.Run.Contracts.PublicSurface;

public sealed record PublicLandingActionDto(
    string Label,
    string Href,
    string Emphasis);

public sealed record PublicLandingRouteDto(
    string Path,
    string Title,
    string Audience,
    string Purpose,
    bool RequiresAuth = false,
    string? GuestFallback = null,
    bool MustExist = true,
    bool PlaceholderAllowed = false,
    string? PlaceholderRequirements = null,
    string? VerificationMode = null,
    string? VerificationFile = null,
    string? VerificationPattern = null,
    string? VerificationPath = null);

public sealed record PublicLandingSectionDto(
    string Id,
    string? Eyebrow,
    string Title,
    string? Intro,
    string Audience,
    string Route,
    string? AssetSlot = null);

public sealed record PublicLandingOverlayDto(
    string Id,
    string Path,
    string Title,
    string Summary);

public sealed record PublicLandingAssetDto(
    string AssetSlot,
    string? SectionId,
    string MediaKind,
    string? PosterUrl,
    string? PosterAvifUrl,
    string? PosterWebpUrl,
    string? MobilePosterUrl,
    string? MobilePosterAvifUrl,
    string? MobilePosterWebpUrl,
    string? LoopUrl,
    string Alt,
    string Caption,
    string MotionPolicy,
    string FallbackStyle);

public sealed record PublicReleaseArtifactDto(
    string Id,
    string Platform,
    string Url,
    string Sha256,
    long? SizeBytes = null,
    string? Head = null,
    string? PlatformId = null,
    string? Rid = null,
    string? Arch = null,
    string? Kind = null,
    string? FileName = null,
    string? InstallAccessClass = null,
    string? PlatformLabel = null,
    string? Format = null,
    string? Flavor = null,
    string? ChannelId = null,
    string? Channel = null,
    string? Version = null,
    string? ReleaseVersion = null,
    string? CompatibilityState = null,
    string? CompatibilityReason = null,
    string? ArtifactId = null,
    string? InstallerMode = null,
    string? PayloadFileName = null,
    string? PayloadDownloadUrl = null,
    string? PayloadSha256 = null,
    long? PayloadSizeBytes = null);

public sealed record PublicReleaseManifestDto(
    string Version,
    string Channel,
    DateTimeOffset PublishedAt,
    IReadOnlyList<PublicReleaseArtifactDto> Downloads,
    string Source = "manifest",
    string Status = "published",
    string? Message = null,
    bool HasFallbackSource = false,
    string? RolloutState = null,
    string? RolloutReason = null,
    string? SupportabilityState = null,
    string? SupportabilitySummary = null,
    string? KnownIssueSummary = null,
    string? FixAvailabilitySummary = null,
    string? ProofStatus = null,
    DateTimeOffset? ProofGeneratedAt = null,
    string? ProofBaseUrl = null,
    IReadOnlyList<string>? ProofJourneys = null,
    IReadOnlyList<string>? ProofRoutes = null,
    DateTimeOffset? GeneratedAt = null,
    string? ContractName = "Chummer.Hub.Registry.Contracts",
    string? PublicVersion = null)
{
    [JsonPropertyName("generationId")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? GenerationId { get; init; }

    [JsonPropertyName("releaseTruth")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public PublicReleaseTruthProjectionDto? ReleaseTruth { get; init; }

    [JsonPropertyName("generated_at")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public DateTimeOffset? GeneratedAtAlias => GeneratedAt;

    [JsonPropertyName("contract_name")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? ContractNameAlias => ContractName;

    [JsonPropertyName("versionRole")]
    public string VersionRole => "artifact_identity";

    [JsonPropertyName("displayVersion")]
    public string DisplayVersion => ResolveDisplayVersion(PublicVersion, Version, Channel, RolloutState, Status, SupportabilityState);

    [JsonPropertyName("displayBuildLabel")]
    public string DisplayBuildLabel => ResolveDisplayBuildLabel(Version, Channel, RolloutState, Status, SupportabilityState);

    [JsonPropertyName("displayChannelLabel")]
    public string DisplayChannelLabel => ResolveDisplayChannelLabel(Channel, RolloutState, Status, SupportabilityState);

    [JsonPropertyName("releaseProof")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public PublicReleaseProofDto? ReleaseProof =>
        string.IsNullOrWhiteSpace(ProofStatus)
        && ProofGeneratedAt is null
        && string.IsNullOrWhiteSpace(ProofBaseUrl)
        && (ProofJourneys is null || ProofJourneys.Count == 0)
        && (ProofRoutes is null || ProofRoutes.Count == 0)
        && ProofUiLocalizationReleaseGate is null
        && ProofFlagshipReadiness is null
            ? null
            : new(
                Status: ProofStatus,
                GeneratedAt: ProofGeneratedAt,
                BaseUrl: ProofBaseUrl,
                JourneysPassed: ProofJourneys,
                ProofRoutes: ProofRoutes,
                UiLocalizationReleaseGate: ProofUiLocalizationReleaseGate,
                FlagshipReadiness: ProofFlagshipReadiness);

    [JsonPropertyName("desktopTupleCoverage")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public JsonElement? DesktopTupleCoverage { get; init; }

    [JsonPropertyName("registryBoundaryCoverage")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public JsonElement? RegistryBoundaryCoverage { get; init; }

    [JsonPropertyName("publicTrustMetrics")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public JsonElement? PublicTrustMetrics { get; init; }

    [JsonPropertyName("installAwareArtifactRegistry")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public JsonElement? InstallAwareArtifactRegistry { get; init; }

    [JsonPropertyName("desktopSurfaceRefs")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public JsonElement? DesktopSurfaceRefs { get; init; }

    [JsonPropertyName("artifactIdentityRegistry")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public JsonElement? ArtifactIdentityRegistry { get; init; }

    [JsonPropertyName("artifactPublicationBindings")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public JsonElement? ArtifactPublicationBindings { get; init; }

    [JsonPropertyName("exchangeLineageRegistry")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public JsonElement? ExchangeLineageRegistry { get; init; }

    [JsonIgnore]
    public JsonElement? ProofUiLocalizationReleaseGate { get; init; }

    [JsonIgnore]
    public JsonElement? ProofFlagshipReadiness { get; init; }

    private static string ResolveDisplayVersion(string? publicVersion, string? version, string? channel, string? rolloutState, string? status, string? supportabilityState)
    {
        if (!string.IsNullOrWhiteSpace(publicVersion)
            && IsPublicStable(channel, rolloutState, status, supportabilityState))
        {
            return publicVersion.Trim();
        }

        return ResolveDisplayVersion(version, channel, rolloutState, status, supportabilityState);
    }

    private static string ResolveDisplayVersion(string? version, string? channel, string? rolloutState, string? status, string? supportabilityState)
        => IsPublicStable(channel, rolloutState, status, supportabilityState)
            ? "current-public-build"
            : string.IsNullOrWhiteSpace(version)
                ? "unpublished"
                : version.Trim();

    private static string ResolveDisplayBuildLabel(string? version, string? channel, string? rolloutState, string? status, string? supportabilityState)
        => IsPublicStable(channel, rolloutState, status, supportabilityState)
            ? "Current public build"
            : string.IsNullOrWhiteSpace(version)
                ? "Unpublished build"
                : $"Build {version.Trim()}";

    private static string ResolveDisplayChannelLabel(string? channel, string? rolloutState, string? status, string? supportabilityState)
        => IsPublicStable(channel, rolloutState, status, supportabilityState)
            ? "Public release"
            : IsPreviewLikeChannel(channel, rolloutState)
                ? "Current release build"
                : string.IsNullOrWhiteSpace(channel)
                    ? "Release channel"
                    : channel.Trim();

    private static bool IsPreviewLikeChannel(string? channel, string? rolloutState)
    {
        var normalizedChannel = (channel ?? string.Empty).Trim();
        var normalizedRolloutState = (rolloutState ?? string.Empty).Trim();
        return string.Equals(normalizedChannel, "preview", StringComparison.OrdinalIgnoreCase)
            || string.Equals(normalizedRolloutState, "promoted_preview", StringComparison.OrdinalIgnoreCase)
            || string.Equals(normalizedChannel, "public_stable", StringComparison.OrdinalIgnoreCase)
            || string.Equals(normalizedChannel, "stable", StringComparison.OrdinalIgnoreCase)
            || string.Equals(normalizedChannel, "docker", StringComparison.OrdinalIgnoreCase)
            || string.Equals(normalizedRolloutState, "public_stable", StringComparison.OrdinalIgnoreCase);
    }

    private static bool IsPublicStable(string? channel, string? rolloutState, string? status, string? supportabilityState)
    {
        var normalizedChannel = (channel ?? string.Empty).Trim();
        var normalizedRolloutState = (rolloutState ?? string.Empty).Trim();
        var stableLanePublished = string.Equals(normalizedRolloutState, "public_stable", StringComparison.OrdinalIgnoreCase)
            || (
                string.Equals(normalizedChannel, "docker", StringComparison.OrdinalIgnoreCase)
                || string.Equals(normalizedChannel, "public_stable", StringComparison.OrdinalIgnoreCase)
                || string.Equals(normalizedChannel, "stable", StringComparison.OrdinalIgnoreCase)
            );
        return stableLanePublished
            && string.Equals((supportabilityState ?? string.Empty).Trim(), "gold_supported", StringComparison.OrdinalIgnoreCase)
            && string.Equals((status ?? string.Empty).Trim(), "published", StringComparison.OrdinalIgnoreCase);
    }
}

public sealed record PublicReleaseProofDto(
    string? Status,
    DateTimeOffset? GeneratedAt,
    string? BaseUrl,
    IReadOnlyList<string>? JourneysPassed,
    IReadOnlyList<string>? ProofRoutes,
    [property: JsonPropertyName("uiLocalizationReleaseGate")]
    JsonElement? UiLocalizationReleaseGate = null,
    [property: JsonPropertyName("flagshipReadiness")]
    JsonElement? FlagshipReadiness = null);

public sealed record PublicFeatureCardDto(
    string Id,
    string Bucket,
    string Title,
    string Summary,
    string Href,
    string Badge,
    string Audience,
    string ImageFamily,
    string AssetSlot,
    string CtaKind = "route",
    string RenderMode = "action",
    string? DetailRoute = null,
    string? FallbackRoute = null,
    string? FallbackLabel = null,
    string? GuestHref = null,
    string? RegisteredHref = null,
    bool ExternalOk = false,
    bool SelfLinkAllowed = false,
    string? ActionLabel = null,
    string? DetailPrimaryHref = null,
    string? DetailPrimaryLabel = null,
    string? ProofNote = null,
    string? MicroProof = null,
    string? Pain = null,
    string? Payoff = null);

public sealed record PublicLandingSurfaceDto(
    string Product,
    string Surface,
    int Version,
    string Headline,
    string Subhead,
    string ProofLine,
    bool NoProviderNames,
    bool NoLtdNames,
    IReadOnlyList<PublicLandingActionDto> HeroCtas,
    IReadOnlyList<PublicLandingActionDto> GuestShellActions,
    IReadOnlyList<string> SecondaryHighlights,
    string? ProductProofEyebrow,
    string? ProductProofIntro,
    string? ProductProofPrimaryLabel,
    string? ProductProofPrimaryHref,
    string? ProductProofSecondaryLabel,
    string? ProductProofSecondaryHref,
    string? ProductProofToplineLabel,
    string? ProductProofResultTitle,
    string? ProductProofResultSummary,
    IReadOnlyList<string> ProductProofTrail,
    IReadOnlyList<PublicLandingRouteDto> PublicRoutes,
    IReadOnlyList<PublicLandingRouteDto> AuthRoutes,
    IReadOnlyList<PublicLandingRouteDto> RegisteredRoutes,
    IReadOnlyList<PublicLandingSectionDto> Sections,
    IReadOnlyList<PublicLandingOverlayDto> RegisteredOverlays,
    IReadOnlyList<PublicLandingAssetDto> Assets,
    string FooterCanonicalSource,
    string FooterGeneratedNote,
    IReadOnlyList<PublicFeatureCardDto> FeatureCards);
