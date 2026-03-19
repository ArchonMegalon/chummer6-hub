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
    string Title,
    string Audience,
    string Route);

public sealed record PublicLandingOverlayDto(
    string Id,
    string Path,
    string Title,
    string Summary);

public sealed record PublicFeatureCardDto(
    string Id,
    string Bucket,
    string Title,
    string Summary,
    string Href,
    string Badge,
    string Audience,
    string ImageFamily,
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
    IReadOnlyList<string> SecondaryHighlights,
    IReadOnlyList<PublicLandingRouteDto> PublicRoutes,
    IReadOnlyList<PublicLandingRouteDto> AuthRoutes,
    IReadOnlyList<PublicLandingRouteDto> RegisteredRoutes,
    IReadOnlyList<PublicLandingSectionDto> Sections,
    IReadOnlyList<PublicLandingOverlayDto> RegisteredOverlays,
    string FooterCanonicalSource,
    string FooterGeneratedNote,
    IReadOnlyList<PublicFeatureCardDto> FeatureCards);
