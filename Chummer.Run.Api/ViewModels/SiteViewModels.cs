using Chummer.Run.Api.Services;
using Chummer.Run.Contracts.Community;
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

public sealed record LandingPageViewModel(
    SiteChromeViewModel Chrome,
    PublicLandingSurfaceDto Surface,
    AssetCatalogViewModel Assets,
    PublicReleaseManifestDto Manifest,
    PublicLandingActionDto PrimaryHeroAction,
    PublicLandingActionDto SecondaryHeroAction,
    IReadOnlyList<PublicFeatureCardDto> Workflows,
    IReadOnlyList<PublicFeatureCardDto> TrustPillars,
    IReadOnlyList<PublicFeatureCardDto> Lanes,
    IReadOnlyList<PublicFeatureCardDto> AvailableToday,
    IReadOnlyList<PublicFeatureCardDto> PreviewItems,
    IReadOnlyList<PublicFeatureCardDto> ComingNext,
    IReadOnlyList<PublicFeatureCardDto> Artifacts);

public sealed record StoryPageViewModel(
    SiteChromeViewModel Chrome,
    PublicLandingSurfaceDto Surface,
    AssetCatalogViewModel Assets,
    IReadOnlyList<PublicFeatureCardDto> TrustPillars,
    IReadOnlyList<PublicFeatureCardDto> Lanes);

public sealed record NowPageViewModel(
    SiteChromeViewModel Chrome,
    PublicLandingSurfaceDto Surface,
    AssetCatalogViewModel Assets,
    IReadOnlyList<PublicFeatureCardDto> AvailableToday,
    IReadOnlyList<PublicFeatureCardDto> Inspectable,
    IReadOnlyList<PublicLandingOverlayDto> SignedInPreview,
    PublicReleaseManifestDto Manifest);

public sealed record HorizonsPageViewModel(
    SiteChromeViewModel Chrome,
    PublicLandingSurfaceDto Surface,
    AssetCatalogViewModel Assets,
    IReadOnlyList<PublicFeatureCardDto> Horizons);

public sealed record ShelfPageViewModel(
    SiteChromeViewModel Chrome,
    PublicLandingSurfaceDto Surface,
    AssetCatalogViewModel Assets,
    string Eyebrow,
    string Heading,
    string Intro,
    IReadOnlyList<PublicFeatureCardDto> Items);

public sealed record DownloadsPageViewModel(
    SiteChromeViewModel Chrome,
    PublicLandingSurfaceDto Surface,
    AssetCatalogViewModel Assets,
    PublicReleaseManifestDto Manifest);

public sealed record ParticipatePageViewModel(
    SiteChromeViewModel Chrome,
    PublicLandingSurfaceDto Surface,
    AssetCatalogViewModel Assets,
    IReadOnlyList<PublicFeatureCardDto> PublicLane,
    IReadOnlyList<PublicFeatureCardDto> SignedInLane);

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
    IReadOnlyList<PublicFeatureCardDto> NowRail,
    IReadOnlyList<PublicFeatureCardDto> HorizonRail);

public sealed record AccountPageViewModel(
    SiteChromeViewModel Chrome,
    HubUserDto User,
    AccountLinkSummaryDto Links,
    HubUserExperienceDto Experience,
    bool GoogleAvailable);

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
