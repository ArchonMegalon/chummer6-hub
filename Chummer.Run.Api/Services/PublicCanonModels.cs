namespace Chummer.Run.Api.Services;

internal sealed class PublicNavigationDocument
{
    public string Product { get; init; } = string.Empty;
    public string Surface { get; init; } = string.Empty;
    public int Version { get; init; }
    public List<PublicNavigationLinkDocument>? PrimaryNav { get; init; }
    public List<PublicNavigationLinkDocument>? SecondaryNav { get; init; }
    public List<PublicNavigationLinkDocument>? UtilityNav { get; init; }
}

internal sealed class PublicNavigationLinkDocument
{
    public string Label { get; init; } = string.Empty;
    public string Href { get; init; } = string.Empty;
}

internal sealed class PublicLandingManifestDocument
{
    public string Product { get; init; } = string.Empty;
    public string Surface { get; init; } = string.Empty;
    public int Version { get; init; }
    public string Headline { get; init; } = string.Empty;
    public string Subhead { get; init; } = string.Empty;
    public string ProofLine { get; init; } = string.Empty;
    public bool NoProviderNames { get; init; }
    public bool NoLtdNames { get; init; }
    public List<PublicLandingActionDocument>? HeroCtas { get; init; }
    public List<string>? SecondaryHighlights { get; init; }
    public List<PublicLandingActionDocument>? GuestShellActions { get; init; }
    public string? ProductProofEyebrow { get; init; }
    public string? ProductProofIntro { get; init; }
    public string? ProductProofPrimaryLabel { get; init; }
    public string? ProductProofPrimaryHref { get; init; }
    public string? ProductProofSecondaryLabel { get; init; }
    public string? ProductProofSecondaryHref { get; init; }
    public string? ProductProofToplineLabel { get; init; }
    public string? ProductProofResultTitle { get; init; }
    public string? ProductProofResultSummary { get; init; }
    public List<string>? ProductProofTrail { get; init; }
    public List<PublicLandingRouteDocument>? PublicRoutes { get; init; }
    public List<PublicLandingRouteDocument>? AuthRoutes { get; init; }
    public List<PublicLandingRouteDocument>? RegisteredRoutes { get; init; }
    public List<PublicLandingSectionDocument>? Sections { get; init; }
    public List<PublicLandingOverlayDocument>? RegisteredOverlays { get; init; }
    public string FooterCanonicalSource { get; init; } = string.Empty;
    public string FooterGeneratedNote { get; init; } = string.Empty;
}

internal sealed class PublicLandingActionDocument
{
    public string Label { get; init; } = string.Empty;
    public string Href { get; init; } = string.Empty;
    public string Emphasis { get; init; } = string.Empty;
}

internal sealed class PublicLandingRouteDocument
{
    public string Path { get; init; } = string.Empty;
    public string Title { get; init; } = string.Empty;
    public string Audience { get; init; } = string.Empty;
    public string Purpose { get; init; } = string.Empty;
    public bool RequiresAuth { get; init; }
    public string? GuestFallback { get; init; }
    public bool MustExist { get; init; } = true;
    public bool PlaceholderAllowed { get; init; }
    public string? PlaceholderRequirements { get; init; }
}

internal sealed class PublicLandingSectionDocument
{
    public string Id { get; init; } = string.Empty;
    public string? Eyebrow { get; init; }
    public string Title { get; init; } = string.Empty;
    public string? Intro { get; init; }
    public string Audience { get; init; } = string.Empty;
    public string Route { get; init; } = string.Empty;
    public string? AssetSlot { get; init; }
}

internal sealed class PublicLandingOverlayDocument
{
    public string Id { get; init; } = string.Empty;
    public string Path { get; init; } = string.Empty;
    public string Title { get; init; } = string.Empty;
    public string Summary { get; init; } = string.Empty;
}

internal sealed class PublicFeatureRegistryDocument
{
    public string Product { get; init; } = string.Empty;
    public string Surface { get; init; } = string.Empty;
    public int Version { get; init; }
    public List<PublicFeatureCardDocument>? Cards { get; init; }
}

internal sealed class PublicFeatureCardDocument
{
    public string Id { get; init; } = string.Empty;
    public string Bucket { get; init; } = string.Empty;
    public string Title { get; init; } = string.Empty;
    public string Summary { get; init; } = string.Empty;
    public string Href { get; init; } = string.Empty;
    public string Badge { get; init; } = string.Empty;
    public string Audience { get; init; } = string.Empty;
    public string ImageFamily { get; init; } = string.Empty;
    public string? AssetSlot { get; init; }
    public string CtaKind { get; init; } = "route";
    public string RenderMode { get; init; } = "action";
    public string? DetailRoute { get; init; }
    public string? FallbackRoute { get; init; }
    public string? FallbackLabel { get; init; }
    public string? GuestHref { get; init; }
    public string? RegisteredHref { get; init; }
    public bool ExternalOk { get; init; }
    public bool SelfLinkAllowed { get; init; }
    public string? ActionLabel { get; init; }
    public string? ProofNote { get; init; }
    public string? Microproof { get; init; }
    public string? Pain { get; init; }
    public string? Payoff { get; init; }
}

internal sealed class PublicAssetRegistryDocument
{
    public string Product { get; init; } = string.Empty;
    public string Surface { get; init; } = string.Empty;
    public int Version { get; init; }
    public List<PublicLandingAssetDocument>? Assets { get; init; }
}

internal sealed class PublicLandingAssetDocument
{
    public string AssetSlot { get; init; } = string.Empty;
    public string? SectionId { get; init; }
    public string MediaKind { get; init; } = string.Empty;
    public string? PosterUrl { get; init; }
    public string? PosterAvifUrl { get; init; }
    public string? PosterWebpUrl { get; init; }
    public string? MobilePosterUrl { get; init; }
    public string? MobilePosterAvifUrl { get; init; }
    public string? MobilePosterWebpUrl { get; init; }
    public string? LoopUrl { get; init; }
    public string Alt { get; init; } = string.Empty;
    public string Caption { get; init; } = string.Empty;
    public string MotionPolicy { get; init; } = string.Empty;
    public string FallbackStyle { get; init; } = string.Empty;
}

internal sealed class PublicTrustContentDocument
{
    public string Product { get; init; } = string.Empty;
    public string Surface { get; init; } = string.Empty;
    public int Version { get; init; }
    public List<PublicTrustPageDocument>? TrustPages { get; init; }
    public List<PublicFaqPageDocument>? FaqPages { get; init; }
}

internal sealed class PublicTrustPageDocument
{
    public string Id { get; init; } = string.Empty;
    public string Eyebrow { get; init; } = string.Empty;
    public string Heading { get; init; } = string.Empty;
    public string Intro { get; init; } = string.Empty;
    public List<PublicTrustActionDocument>? Actions { get; init; }
    public List<PublicTrustSectionDocument>? Sections { get; init; }
}

internal sealed class PublicTrustActionDocument
{
    public string Label { get; init; } = string.Empty;
    public string Href { get; init; } = string.Empty;
    public string Tone { get; init; } = string.Empty;
}

internal sealed class PublicTrustSectionDocument
{
    public string Id { get; init; } = string.Empty;
    public string Eyebrow { get; init; } = string.Empty;
    public string Heading { get; init; } = string.Empty;
    public string Body { get; init; } = string.Empty;
    public List<string>? Bullets { get; init; }
}

internal sealed class PublicFaqPageDocument
{
    public string Id { get; init; } = string.Empty;
    public string Eyebrow { get; init; } = string.Empty;
    public string Heading { get; init; } = string.Empty;
    public string Intro { get; init; } = string.Empty;
    public List<PublicTrustActionDocument>? Actions { get; init; }
    public List<PublicFaqSectionDocument>? Sections { get; init; }
}

internal sealed class PublicFaqSectionDocument
{
    public string Title { get; init; } = string.Empty;
    public List<PublicFaqEntryDocument>? Entries { get; init; }
}

internal sealed class PublicFaqEntryDocument
{
    public string Question { get; init; } = string.Empty;
    public string Answer { get; init; } = string.Empty;
}

internal sealed class PublicReleaseExperienceDocument
{
    public string Product { get; init; } = string.Empty;
    public string Surface { get; init; } = string.Empty;
    public int Version { get; init; }
    public List<string>? GuestReadableChannels { get; init; }
    public string ReleaseNotesSummary { get; init; } = string.Empty;
    public string KnownIssuesLabel { get; init; } = string.Empty;
    public string KnownIssuesHref { get; init; } = string.Empty;
    public string InstallHelpLabel { get; init; } = string.Empty;
    public string InstallHelpHref { get; init; } = string.Empty;
    public string UpdatePostureSummary { get; init; } = string.Empty;
    public string DefaultPublicChannelLabel { get; init; } = "Preview channel";
    public string UnpublishedBuildLabel { get; init; } = "Current preview build";
    public string BuildLabelPrefix { get; init; } = "Build";
    public List<PublicReleaseChannelLabelDocument>? PublicChannelLabels { get; init; }
    public string GuestGateHeading { get; init; } = string.Empty;
    public string GuestGateSummary { get; init; } = string.Empty;
    public string GuestGatePrimaryLabel { get; init; } = string.Empty;
    public string GuestGateSecondaryLabel { get; init; } = string.Empty;
    public string SignedInDispatchHeading { get; init; } = string.Empty;
    public string SignedInDispatchSummary { get; init; } = string.Empty;
    public List<string>? SignedInDispatchSteps { get; init; }
    public List<string>? InstallSteps { get; init; }
    public List<string>? AccountRequiredInstallSteps { get; init; }
    public List<string>? WindowsRequirements { get; init; }
    public List<string>? LinuxRequirements { get; init; }
    public List<string>? MacosRequirements { get; init; }
}

internal sealed class PublicReleaseChannelLabelDocument
{
    public string Id { get; init; } = string.Empty;
    public string Label { get; init; } = string.Empty;
}
