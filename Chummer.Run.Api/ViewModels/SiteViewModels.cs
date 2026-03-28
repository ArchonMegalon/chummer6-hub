using Chummer.Run.Api.Services;
using Chummer.Run.Api.Contracts;
using Chummer.Campaign.Contracts;
using Chummer.Control.Contracts.Support;
using Chummer.Run.Contracts.Community;
using Chummer.Hub.Registry.Contracts.InstallLinking;
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

public sealed record ReleaseDisplayViewModel(
    string ChannelLabel,
    string BuildLabel,
    string PublishedLabel);

public sealed record ReleaseExperienceViewModel(
    ReleaseDisplayViewModel Display,
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
    string? PlatformShelfNoticeTitle,
    string? PlatformShelfNoticeSummary,
    string? RequestedPlatformLabel,
    string GuestGateHeading,
    string GuestGateSummary,
    string GuestGatePrimaryLabel,
    string GuestGatePrimaryHref,
    string GuestGateSecondaryLabel,
    string GuestGateSecondaryHref,
    string PublicPreviewPrimaryLabel,
    string PublicPreviewPrimaryHref,
    string NoBuildPrimaryLabel,
    string NoBuildPrimaryHref,
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
    ReleaseExperienceViewModel ReleaseExperience,
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
    IReadOnlyList<ResolvedPublicCardViewModel> Workflows,
    IReadOnlyList<PublicFeatureCardDto> TrustPillars,
    IReadOnlyList<ResolvedPublicCardViewModel> Lanes);

public sealed record NowPageViewModel(
    SiteChromeViewModel Chrome,
    PublicLandingSurfaceDto Surface,
    AssetCatalogViewModel Assets,
    ReleaseExperienceViewModel ReleaseExperience,
    IReadOnlyList<ResolvedPublicCardViewModel> ProofModules,
    IReadOnlyList<ResolvedPublicCardViewModel> AvailableToday,
    IReadOnlyList<ResolvedPublicCardViewModel> Inspectable,
    IReadOnlyList<PublicLandingOverlayDto> SignedInPreview,
    PublicReleaseManifestDto Manifest,
    CampaignOsLocalProofSnapshot? CampaignOsProof = null,
    SignedInTrustStatusPanelViewModel? SignedInStatus = null);

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
    ReleaseExperienceViewModel ReleaseExperience,
    SignedInTrustStatusPanelViewModel? SignedInStatus = null);

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
    ReleaseDisplayViewModel Display,
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

public sealed record SignedInTrustStatusRowViewModel(
    string Label,
    string Value);

public sealed record SignedInTrustStatusPanelViewModel(
    string Eyebrow,
    string Heading,
    string Summary,
    IReadOnlyList<SignedInTrustStatusRowViewModel> Rows,
    TrustPageActionViewModel PrimaryAction,
    TrustPageActionViewModel? SecondaryAction = null);

public sealed record SupportIntakeOptionViewModel(
    string Value,
    string Label,
    string Description);

public sealed record SupportIntakeViewModel(
    string ActionHref,
    string Heading,
    string Intro,
    bool Authenticated,
    string AccountSupportHref,
    string AccountSupportLabel,
    string ResponseExpectation,
    string? SubmissionNotice,
    string AttachmentHelp,
    IReadOnlyList<SupportIntakeOptionViewModel> Options,
    string? DefaultKind = null,
    string? DefaultTitle = null,
    string? DefaultSummary = null,
    string? DefaultDetail = null,
    string? DefaultPlatform = null,
    string? DefaultApplicationVersion = null,
    string? DefaultInstallationId = null,
    string? DefaultReleaseChannel = null,
    string? DefaultHeadId = null,
    string? DefaultArch = null,
    string? ContextHint = null);

public sealed record SupportSubmittedPageViewModel(
    SiteChromeViewModel Chrome,
    string Eyebrow,
    string Heading,
    string Intro,
    string CaseId,
    string StatusLabel,
    string ResponseExpectation,
    IReadOnlyList<string> Highlights,
    IReadOnlyList<TrustPageActionViewModel> Actions,
    IReadOnlyList<SupportCaseAttachmentProjection> Attachments,
    SupportCasePresentationViewModel? TrackedCaseSummary = null);

public sealed record TrustPageViewModel(
    string PageId,
    SiteChromeViewModel Chrome,
    string Eyebrow,
    string Heading,
    string Intro,
    IReadOnlyList<TrustPageSectionViewModel> Sections,
    IReadOnlyList<TrustPageActionViewModel> Actions,
    string? EffectiveDate = null,
    string? UpdatedDate = null,
    IReadOnlyList<string>? SummaryPoints = null,
    SupportIntakeViewModel? SupportIntake = null,
    SignedInTrustStatusPanelViewModel? SignedInStatus = null);

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

public sealed record FeatureDetailFactViewModel(
    string Label,
    string Body);

public sealed record SectionLinkViewModel(
    string Key,
    string Label,
    string Href,
    bool Current);

public sealed record FeatureDetailPageViewModel(
    SiteChromeViewModel Chrome,
    string Family,
    string Eyebrow,
    string Heading,
    string Intro,
    string StatusEyebrow,
    string StatusHeading,
    string StatusLabel,
    PublicLandingAssetDto? Asset,
    ResolvedPublicActionViewModel PrimaryAction,
    TrustPageActionViewModel? SecondaryAction,
    IReadOnlyList<FeatureDetailFactViewModel> Facts,
    string? Pain,
    string? Payoff,
    string? ProofNote,
    IReadOnlyList<string> MicroProof);

public sealed record LeaderboardsPageViewModel(
    SiteChromeViewModel Chrome,
    IReadOnlyList<LeaderboardRowDto> Individuals,
    IReadOnlyList<SponsorRankLeaderboardRowDto> SponsorRank,
    IReadOnlyList<GroupLeaderboardRowDto> Groups,
    IReadOnlyList<QuestDto> Quests);

public sealed record HomePageViewModel(
    SiteChromeViewModel Chrome,
    string CurrentSection,
    IReadOnlyList<SectionLinkViewModel> Sections,
    PublicLandingSurfaceDto Surface,
    AssetCatalogViewModel Assets,
    HubUserDto User,
    AccountLinkSummaryDto Links,
    HubUserExperienceDto Experience,
    InstallLinkingSummaryDto InstallLinking,
    IReadOnlyList<SupportCaseProjection> SupportCases,
    IReadOnlyList<SupportCasePresentationViewModel> SupportCaseSummaries,
    AccountCampaignSummary CampaignSpine,
    HomePrimaryActionViewModel PrimaryAction,
    IReadOnlyList<ResolvedPublicCardViewModel> NowRail,
    IReadOnlyList<ResolvedPublicCardViewModel> HorizonRail);

public sealed record SupportCasePresentationViewModel(
    SupportCaseProjection Case,
    string StatusLabel,
    string StageLabel,
    string NextSafeAction,
    string ClosureSummary,
    string VerificationSummary,
    string DetailHref,
    string PrimaryActionLabel,
    string PrimaryActionHref,
    string UpdatedLabel,
    string? FixedReleaseLabel,
    string? AffectedInstallSummary,
    string FollowUpLaneSummary,
    string ReleaseProgressSummary,
    IReadOnlyList<SupportCaseTimelineHighlightViewModel> TimelineHighlights,
    bool ReporterActionNeeded,
    bool CanVerifyFix,
    string InstallReadinessSummary,
    bool FixReadyOnLinkedInstall,
    bool NeedsInstallUpdate,
    bool NeedsLinkedInstall);

public sealed record SupportCaseDigestViewModel(
    string CaseId,
    string Title,
    string Summary,
    string StatusLabel,
    string StageLabel,
    string NextSafeAction,
    string ClosureSummary,
    string VerificationSummary,
    string DetailHref,
    string PrimaryActionLabel,
    string PrimaryActionHref,
    string UpdatedLabel,
    string? FixedReleaseLabel,
    string? AffectedInstallSummary,
    string FollowUpLaneSummary,
    string ReleaseProgressSummary,
    bool ReporterActionNeeded,
    bool CanVerifyFix,
    string InstallReadinessSummary,
    bool FixReadyOnLinkedInstall,
    bool NeedsInstallUpdate,
    bool NeedsLinkedInstall);

public sealed record SupportCaseTimelineHighlightViewModel(
    string Label,
    string Summary,
    string OccurredLabel);

public sealed record AccountPageViewModel(
    SiteChromeViewModel Chrome,
    string CurrentSection,
    IReadOnlyList<SectionLinkViewModel> CoreSections,
    IReadOnlyList<SectionLinkViewModel> SecondarySections,
    HubUserDto User,
    AccountLinkSummaryDto Links,
    HubUserExperienceDto Experience,
    bool GoogleAvailable,
    InstallLinkingSummaryDto InstallLinking,
    IReadOnlyList<SupportCaseProjection> SupportCases,
    IReadOnlyList<SupportCasePresentationViewModel> SupportCaseSummaries,
    SupportCaseProjection? SelectedSupportCase,
    SupportCasePresentationViewModel? SelectedSupportCaseSummary,
    AccountCampaignSummary CampaignSpine,
    CampaignWorkspaceProjection? SelectedWorkspace = null,
    CampaignWorkspaceServerPlaneProjection? SelectedWorkspaceServerPlane = null,
    RunProjection? SelectedRun = null,
    BuildLabHandoffProjection? SelectedBuildLabHandoff = null,
    RulesNavigatorAnswerProjection? SelectedRulesNavigatorAnswer = null,
    CreatorPublicationProjection? SelectedCreatorPublication = null);

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
    string SecondaryHref,
    string? StateLabel = null,
    IReadOnlyList<string>? Highlights = null);

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
