using Chummer.Run.Api.Services;
using Chummer.Run.Contracts.Community;
using Chummer.Run.Contracts.InstallLinking;
using Chummer.Run.Contracts.Leaderboards;
using Chummer.Run.Contracts.PublicSurface;

namespace Chummer.Run.Api.ViewModels;

public sealed record SiteChromeActionViewModel(
    string Label,
    string Href,
    string Tone,
    bool Current = false);

public sealed record SiteChromeViewModel(
    string Title,
    string Description,
    string CurrentPath,
    IReadOnlyList<PublicNavigationLink> PrimaryNavigation,
    IReadOnlyList<PublicNavigationLink> SecondaryNavigation,
    IReadOnlyList<PublicNavigationLink> UtilityNavigation,
    IReadOnlyList<SiteChromeActionViewModel> HeaderActions,
    SiteChromeActionViewModel? PublicPrimaryCta,
    bool Authenticated,
    string? SignedInLabel,
    string FooterCanonicalSource,
    string FooterGeneratedNote);

public sealed class AssetCatalogViewModel
{
    private readonly IReadOnlyDictionary<string, PublicLandingAssetDto> _assetsBySlot;

    public AssetCatalogViewModel(IReadOnlyList<PublicLandingAssetDto> assets)
    {
        _assetsBySlot = assets.ToDictionary(static asset => asset.AssetSlot, StringComparer.Ordinal);
    }

    public PublicLandingAssetDto? BySlot(string slot)
        => _assetsBySlot.TryGetValue(slot, out var asset) ? asset : null;

    public PublicLandingAssetDto? ForCard(PublicFeatureCardDto card)
        => BySlot(card.AssetSlot);
}

public sealed record ResolvedPublicActionViewModel(
    string Label,
    string Href,
    string Tone,
    bool External = false,
    bool Current = false);

public sealed record ResolvedPublicCardViewModel(
    PublicFeatureCardDto Card,
    PublicLandingAssetDto? Asset,
    ResolvedPublicActionViewModel Action);

public sealed record ReleaseOptionViewModel(
    PublicReleaseArtifactDto Artifact,
    string Title,
    string DispatchHref,
    string DirectFileHref,
    string PlatformLabel,
    string HeadLabel,
    string SizeLabel,
    string SupportLine,
    string ActionLabel,
    string? ShaPreview,
    bool Installer,
    string InstallAccessClass,
    bool RequiresAccount,
    bool GuestDownloadAllowed);

public sealed record ReleaseExperienceViewModel(
    ReleaseOptionViewModel? Recommended,
    IReadOnlyList<ReleaseOptionViewModel> Alternatives,
    IReadOnlyList<ReleaseOptionViewModel> OtherPlatforms,
    IReadOnlyList<ReleaseOptionViewModel> ManualPackages,
    string ReleaseNotesSummary,
    string KnownIssuesLabel,
    string KnownIssuesHref,
    string InstallHelpLabel,
    string InstallHelpHref,
    string UpdatePostureSummary,
    bool GuestDownloadAvailable,
    string GuestGateHeading,
    string GuestGateSummary,
    string GuestGatePrimaryLabel,
    string GuestGatePrimaryHref,
    string GuestGateSecondaryLabel,
    string GuestGateSecondaryHref,
    string SignedInDispatchHeading,
    string SignedInDispatchSummary,
    IReadOnlyList<string> SignedInDispatchSteps,
    IReadOnlyList<string> InstallSteps,
    IReadOnlyList<string> SystemRequirements);

public sealed record HomePrimaryActionViewModel(
    string Eyebrow,
    string Title,
    string Summary,
    string Label,
    string Href,
    string Tone);

public sealed record LandingPageViewModel(
    SiteChromeViewModel Chrome,
    PublicLandingSurfaceDto Surface,
    AssetCatalogViewModel Assets,
    PublicReleaseManifestDto Manifest,
    PublicLandingActionDto PrimaryHeroAction,
    PublicLandingActionDto SecondaryHeroAction,
    IReadOnlyList<ResolvedPublicCardViewModel> Workflows,
    IReadOnlyList<PublicFeatureCardDto> TrustPillars,
    IReadOnlyList<ResolvedPublicCardViewModel> Lanes,
    IReadOnlyList<ResolvedPublicCardViewModel> AvailableToday,
    IReadOnlyList<ResolvedPublicCardViewModel> PreviewItems,
    IReadOnlyList<ResolvedPublicCardViewModel> ComingNext,
    IReadOnlyList<ResolvedPublicCardViewModel> Artifacts);

public sealed record StoryPageViewModel(
    SiteChromeViewModel Chrome,
    PublicLandingSurfaceDto Surface,
    AssetCatalogViewModel Assets,
    IReadOnlyList<PublicFeatureCardDto> TrustPillars,
    IReadOnlyList<ResolvedPublicCardViewModel> Lanes);

public sealed record NowPageViewModel(
    SiteChromeViewModel Chrome,
    PublicLandingSurfaceDto Surface,
    AssetCatalogViewModel Assets,
    IReadOnlyList<ResolvedPublicCardViewModel> AvailableToday,
    IReadOnlyList<ResolvedPublicCardViewModel> Inspectable,
    IReadOnlyList<PublicLandingOverlayDto> SignedInPreview,
    PublicReleaseManifestDto Manifest);

public sealed record HorizonsPageViewModel(
    SiteChromeViewModel Chrome,
    PublicLandingSurfaceDto Surface,
    AssetCatalogViewModel Assets,
    IReadOnlyList<ResolvedPublicCardViewModel> Horizons);

public sealed record ShelfPageViewModel(
    SiteChromeViewModel Chrome,
    PublicLandingSurfaceDto Surface,
    AssetCatalogViewModel Assets,
    string Eyebrow,
    string Heading,
    string Intro,
    IReadOnlyList<ResolvedPublicCardViewModel> Items);

public sealed record DownloadsPageViewModel(
    SiteChromeViewModel Chrome,
    PublicLandingSurfaceDto Surface,
    AssetCatalogViewModel Assets,
    PublicReleaseManifestDto Manifest,
    ReleaseExperienceViewModel ReleaseExperience);

public sealed record DownloadDispatchPageViewModel(
    SiteChromeViewModel Chrome,
    string Heading,
    string Summary,
    string ArtifactTitle,
    string ArtifactSupportLine,
    string DownloadHref,
    string DownloadLabel,
    string AccountHref,
    string AccountLabel,
    string HelpHref,
    string HelpLabel,
    string Channel,
    string Version,
    string PlatformLabel,
    string HeadLabel,
    string? ClaimCode,
    DateTimeOffset? ClaimCodeExpiresAtUtc,
    IReadOnlyList<string> Steps);

public sealed record TrustPageSectionViewModel(
    string Id,
    string Eyebrow,
    string Heading,
    string Body,
    IReadOnlyList<string>? Bullets = null);

public sealed record TrustPageActionViewModel(
    string Label,
    string Href,
    string Tone);

public sealed record TrustPageViewModel(
    SiteChromeViewModel Chrome,
    string Eyebrow,
    string Heading,
    string Intro,
    IReadOnlyList<TrustPageSectionViewModel> Sections,
    IReadOnlyList<TrustPageActionViewModel> Actions);

public sealed record FaqEntryViewModel(
    string Question,
    string Answer);

public sealed record FaqSectionViewModel(
    string Title,
    IReadOnlyList<FaqEntryViewModel> Entries);

public sealed record FaqPageViewModel(
    SiteChromeViewModel Chrome,
    string Eyebrow,
    string Heading,
    string Intro,
    IReadOnlyList<FaqSectionViewModel> Sections,
    IReadOnlyList<TrustPageActionViewModel> Actions);

public sealed record ParticipatePageViewModel(
    SiteChromeViewModel Chrome,
    PublicLandingSurfaceDto Surface,
    AssetCatalogViewModel Assets,
    IReadOnlyList<ResolvedPublicCardViewModel> PublicLane,
    IReadOnlyList<ResolvedPublicCardViewModel> SignedInLane);

public sealed record LeaderboardsPageViewModel(
    SiteChromeViewModel Chrome,
    IReadOnlyList<LeaderboardRowDto> Individuals,
    IReadOnlyList<SponsorRankLeaderboardRowDto> SponsorRank,
    IReadOnlyList<GroupLeaderboardRowDto> Groups,
    IReadOnlyList<QuestDto> Quests);

public sealed record HomePageViewModel(
    SiteChromeViewModel Chrome,
    PublicLandingSurfaceDto Surface,
    AssetCatalogViewModel Assets,
    HubUserDto User,
    AccountLinkSummaryDto Links,
    HubUserExperienceDto Experience,
    InstallLinkingSummaryDto InstallLinking,
    HomePrimaryActionViewModel PrimaryAction,
    IReadOnlyList<ResolvedPublicCardViewModel> NowRail,
    IReadOnlyList<ResolvedPublicCardViewModel> HorizonRail);

public sealed record AccountPageViewModel(
    SiteChromeViewModel Chrome,
    HubUserDto User,
    AccountLinkSummaryDto Links,
    HubUserExperienceDto Experience,
    bool GoogleAvailable,
    InstallLinkingSummaryDto InstallLinking);

public sealed record AuthPageViewModel(
    SiteChromeViewModel Chrome,
    string Heading,
    string SupportLine,
    string NextPath,
    bool CreateAccount,
    bool GoogleAvailable,
    string? GoogleUnavailableReason,
    string GoogleStartHref);

public sealed record AuthMessagePageViewModel(
    SiteChromeViewModel Chrome,
    string Heading,
    string SupportLine,
    string? Notice,
    string PrimaryLabel,
    string PrimaryHref,
    string SecondaryLabel,
    string SecondaryHref);

public sealed record GoogleMergePageViewModel(
    SiteChromeViewModel Chrome,
    string ExistingDisplayName,
    string VerifiedEmail,
    string NextPath,
    string MergeToken);

public sealed record ParticipationConsolePageViewModel(
    SiteChromeViewModel Chrome,
    HubUserDto User,
    AccountLinkSummaryDto Links,
    HubUserExperienceDto Experience);
