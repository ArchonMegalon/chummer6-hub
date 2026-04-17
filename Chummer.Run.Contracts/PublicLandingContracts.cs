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
    string? PlaceholderRequirements = null);

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
    string? Arch = null,
    string? Kind = null,
    string? FileName = null,
    string? InstallAccessClass = null);

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
    string? ContractName = "Chummer.Hub.Registry.Contracts")
{
    [JsonPropertyName("generated_at")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public DateTimeOffset? GeneratedAtAlias => GeneratedAt;

    [JsonPropertyName("contract_name")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? ContractNameAlias => ContractName;

    [JsonPropertyName("releaseProof")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public PublicReleaseProofDto? ReleaseProof =>
        string.IsNullOrWhiteSpace(ProofStatus)
        && ProofGeneratedAt is null
        && string.IsNullOrWhiteSpace(ProofBaseUrl)
        && (ProofJourneys is null || ProofJourneys.Count == 0)
        && (ProofRoutes is null || ProofRoutes.Count == 0)
            ? null
            : new(
                Status: ProofStatus,
                GeneratedAt: ProofGeneratedAt,
                BaseUrl: ProofBaseUrl,
                JourneysPassed: ProofJourneys,
                ProofRoutes: ProofRoutes);
}

public sealed record PublicReleaseProofDto(
    string? Status,
    DateTimeOffset? GeneratedAt,
    string? BaseUrl,
    IReadOnlyList<string>? JourneysPassed,
    IReadOnlyList<string>? ProofRoutes);

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
