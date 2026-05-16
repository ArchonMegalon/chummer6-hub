using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.Services.KarmaForge;
using Chummer.Run.Api.Contracts;
using Chummer.Campaign.Contracts;
using Chummer.Control.Contracts.Support;
using Chummer.Run.Contracts.Boosters;
using Chummer.Run.Contracts.Community;
using Chummer.Run.Contracts.Ledger;
using Chummer.Hub.Registry.Contracts;
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
    string FooterGeneratedNote,
    IReadOnlyList<PublicNavigationLink>? PublicSignalNavigation = null,
    string? HelpHref = null,
    string? HelpLabel = null,
    string? ContactHref = null,
    string? ContactLabel = null);

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

public sealed record PublicAccessPostureViewModel(
    bool GuestInstallAvailable,
    bool AccountRequiredInstallAvailable,
    string AvailabilitySummary,
    string AccountValueSummary,
    string CreateAccountSummary,
    string SignInSummary,
    string DownloadFaqAnswer,
    string AccountFaqAnswer);

public sealed record ReleasePlatformAvailabilityViewModel(
    string PlatformId,
    string PlatformLabel,
    string StatusLabel,
    string Summary,
    string PrimaryPackageLabel,
    string SupportabilityLabel,
    bool PubliclyAvailable,
    bool CurrentDevice);

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
    bool RequestedPlatformHasPublicDownload,
    string? PlatformShelfNoticeTitle,
    string? PlatformShelfNoticeSummary,
    string? RequestedPlatformLabel,
    IReadOnlyList<ReleasePlatformAvailabilityViewModel> PlatformAvailability,
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

public sealed record FlagshipCoverageCardViewModel(
    string Id,
    string Label,
    string Summary,
    string CurrentTitle,
    string CurrentBody,
    string TargetTitle,
    string TargetBody,
    string Href,
    string ActionLabel);

public sealed record FlagshipCoverageStripViewModel(
    string Eyebrow,
    string Heading,
    string Intro,
    IReadOnlyList<FlagshipCoverageCardViewModel> Cards);

public sealed record BlackLedgerPublicStatViewModel(
    string Id,
    string Title,
    string Value,
    string Scope,
    string ScopeKey,
    string Period,
    string SampleSize,
    int SampleCount,
    string Confidence,
    string ConfidenceKey,
    string PrivacyNote,
    string Source,
    BlackLedgerPublicStatSourceViewModel SourceDetail,
    string Status,
    string Href);

public sealed record BlackLedgerPublicStatSourceViewModel(
    string Kind,
    string Label,
    string ProvenanceSummary,
    bool PreviewOnly,
    bool PublicSafe);

public sealed record BlackLedgerModuleViewModel(
    string Id,
    string Title,
    string Summary,
    string Href,
    string StatusLabel);

public sealed record BlackLedgerCloseoutViewModel(
    string Title,
    string Summary,
    string Href,
    string StatusLabel);

public sealed record BlackLedgerDistrictViewModel(
    string Id,
    string Name,
    string PolygonPoints,
    string DominantFaction,
    int Influence,
    int Heat,
    string Summary,
    int CenterX,
    int CenterY,
    int Confidence,
    int Volatility,
    string Trend,
    int DeltaSinceLastTick);

public sealed record BlackLedgerFactionViewModel(
    string Id,
    string PublicName,
    string Type,
    string FactionLeader,
    string FieldGm,
    string IntelProvider,
    IReadOnlyList<string> PublicSignals,
    string ColorPrimary,
    string ColorSecondary,
    string Icon);

public sealed record BlackLedgerMapModeViewModel(
    string Id,
    string Label,
    string Summary,
    bool Active);

public sealed record BlackLedgerMapEventViewModel(
    string EventId,
    string EventType,
    string RegionId,
    string Title,
    string Summary,
    int Severity,
    int Confidence,
    string Status,
    int X,
    int Y,
    bool NewThisTurn,
    string SourceReceiptId,
    string SourceReceiptHref,
    string? DispatchHref);

public sealed record BlackLedgerMapArcViewModel(
    string ArcId,
    string SourceRegionId,
    string TargetRegionId,
    string ArcType,
    int Intensity,
    string Direction,
    string Summary);

public sealed record BlackLedgerMapReplayStepViewModel(
    int Turn,
    string Label,
    string Summary,
    bool Current);

public sealed record BlackLedgerCommandMapViewModel(
    string WorldId,
    string RenderMode,
    string CurrentMode,
    IReadOnlyList<BlackLedgerMapModeViewModel> Modes,
    IReadOnlyList<BlackLedgerMapEventViewModel> Events,
    IReadOnlyList<BlackLedgerMapArcViewModel> Arcs,
    IReadOnlyList<BlackLedgerMapReplayStepViewModel> ReplaySteps,
    string AccessibilityNote,
    string PerformanceNote,
    string PublicSafetyNote);

public sealed record BlackLedgerTickEffectViewModel(
    string Target,
    string Metric,
    int Delta,
    string PublicReason);

public sealed record BlackLedgerTickReceiptViewModel(
    string WorldId,
    int Turn,
    string ReceiptId,
    string Mode,
    string Summary,
    string InputStateHash,
    string DecisionPacketHash,
    bool PrivacyPassed,
    IReadOnlyList<string> BlockedFields,
    string OutputStateHash,
    string CreatedAtUtc,
    IReadOnlyList<BlackLedgerTickEffectViewModel> Effects);

public sealed record BlackLedgerTurnNavigationViewModel(
    int Turn,
    string Label,
    string Href,
    bool Current,
    bool PreviewOnly);

public sealed record BlackLedgerStewardshipPostViewModel(
    string Id,
    string PublicLabel,
    string HolderType,
    string FallbackPersonality,
    string PublicSummary,
    bool HumanOverrideAvailable);

public sealed record BlackLedgerStewardshipTransferReceiptViewModel(
    string ReceiptType,
    string PostId,
    string OldHolder,
    string NewHolder,
    string NewHolderType,
    string OccurredAt,
    string Reason,
    string OperatorId,
    string PublicVisibility);

public sealed record BlackLedgerDispatchViewModel(
    string DispatchId,
    string WorldId,
    int Turn,
    string Type,
    string Scope,
    string SourceReceiptId,
    string SourceReceiptHref,
    string Title,
    string Summary,
    string Body,
    IReadOnlyList<string> InvolvedFactions,
    IReadOnlyList<string> InvolvedDistricts,
    IReadOnlyList<string> PackagePressureLinks,
    string PrivacyStatus,
    string GeneratedBy,
    string HumanReviewStatus,
    string CreatedAtUtc,
    bool PublicSafe,
    bool AiGenerated,
    string Href);

public sealed record BlackLedgerWorldPreviewViewModel(
    string WorldId,
    string PublicName,
    string Status,
    int CurrentTurn,
    string TurnHeadline,
    string SafetyNote,
    string MapNote,
    bool DeterministicPreview,
    IReadOnlyList<BlackLedgerTurnNavigationViewModel> TurnNavigation,
    IReadOnlyList<BlackLedgerDistrictViewModel> Districts,
    IReadOnlyList<BlackLedgerFactionViewModel> Factions,
    IReadOnlyList<BlackLedgerStewardshipPostViewModel> StewardshipPosts,
    BlackLedgerStewardshipTransferReceiptViewModel? StewardshipTransferPreview,
    BlackLedgerTickReceiptViewModel? LastTick);

public sealed record LandingPageViewModel(
    SiteChromeViewModel Chrome,
    PublicLandingSurfaceDto Surface,
    AssetCatalogViewModel Assets,
    PublicReleaseManifestDto Manifest,
    ReleaseExperienceViewModel ReleaseExperience,
    PublicTrustPulsePanelViewModel? TrustPulse,
    SignedInTrustStatusPanelViewModel? SignedInStatus,
    PublicLandingActionDto PrimaryHeroAction,
    PublicLandingActionDto SecondaryHeroAction,
    IReadOnlyList<ResolvedPublicCardViewModel> Workflows,
    IReadOnlyList<PublicFeatureCardDto> TrustPillars,
    IReadOnlyList<ResolvedPublicCardViewModel> Lanes,
    IReadOnlyList<ResolvedPublicCardViewModel> AvailableToday,
    IReadOnlyList<ResolvedPublicCardViewModel> PreviewItems,
    IReadOnlyList<ResolvedPublicCardViewModel> ComingNext,
    IReadOnlyList<ResolvedPublicCardViewModel> Artifacts,
    FlagshipCoverageStripViewModel FlagshipCoverage,
    IReadOnlyList<BlackLedgerPublicStatViewModel> BlackLedgerStats,
    BlackLedgerWorldPreviewViewModel? BlackLedgerWorld = null,
    BlackLedgerDispatchViewModel? LatestBlackLedgerDispatch = null,
    AccountCampaignSummary? CampaignSpine = null,
    PublicAccessPostureViewModel? AccessPosture = null);

public sealed record BlackLedgerHubPageViewModel(
    SiteChromeViewModel Chrome,
    string Eyebrow,
    string Heading,
    string Intro,
    string CurrentSection,
    BlackLedgerWorldPreviewViewModel? World,
    BlackLedgerFactionViewModel? SelectedFaction,
    IReadOnlyList<BlackLedgerPublicStatViewModel> Stats,
    IReadOnlyList<BlackLedgerModuleViewModel> Modules,
    IReadOnlyList<BlackLedgerCloseoutViewModel> Closeouts,
    IReadOnlyList<BlackLedgerDispatchViewModel> Dispatches,
    BlackLedgerDispatchViewModel? SelectedDispatch,
    BlackLedgerCommandMapViewModel? CommandMap,
    TrustPageActionViewModel PrimaryAction,
    TrustPageActionViewModel SecondaryAction,
    PublicTrustPulsePanelViewModel? TrustPulse = null,
    SignedInTrustStatusPanelViewModel? SignedInStatus = null);

public sealed record BlackLedgerFactionWorkspaceTabViewModel(
    string Label,
    string Href,
    bool Current);

public sealed record BlackLedgerFactionWorkspacePageViewModel(
    SiteChromeViewModel Chrome,
    string Eyebrow,
    string Heading,
    string Intro,
    string CurrentSection,
    BlackLedgerWorldPreviewViewModel? World,
    BlackLedgerFactionViewModel Faction,
    IReadOnlyList<string> CoveredDistricts,
    IReadOnlyList<string> PrivateLabels,
    IReadOnlyList<string> PrivateLoreNotes,
    IReadOnlyList<BlackLedgerDispatchViewModel> Dispatches,
    IReadOnlyList<BlackLedgerFactionWorkspaceTabViewModel> Tabs,
    string PublicProfileHref,
    string PrivacyNote,
    PublicTrustPulsePanelViewModel? TrustPulse = null,
    SignedInTrustStatusPanelViewModel? SignedInStatus = null);

public sealed record AnarchyRunnerProfileViewModel(
    string RunnerId,
    string Handle,
    string Concept,
    string MetatypeOrIdentityTag,
    IReadOnlyList<string> ArchetypeTags,
    IReadOnlyList<string> NarrativeCues,
    IReadOnlyList<string> Capabilities,
    IReadOnlyList<string> ShadowAmps,
    IReadOnlyList<string> GearTags,
    IReadOnlyList<string> Contacts,
    IReadOnlyList<string> Complications,
    IReadOnlyList<string> FactionLinks,
    string DebtHeat,
    IReadOnlyList<string> LedgerFlags,
    string Notes,
    string RulesetId,
    string VerdictLabel,
    string PostureLabel);

public sealed record AnarchyLedgerStatViewModel(
    string Label,
    string Value,
    string Summary);

public sealed record AnarchyExplainReceiptViewModel(
    string ReceiptId,
    string SourceReceiptId,
    string RulesetId,
    string Status,
    IReadOnlyList<string> ProvenanceNotes,
    string CreatedAtUtc);

public sealed record AnarchyPageViewModel(
    SiteChromeViewModel Chrome,
    string Eyebrow,
    string Heading,
    string Intro,
    string CurrentSection,
    string RulesetId,
    string VerdictLabel,
    string ScopeLabel,
    AnarchyRunnerProfileViewModel FeaturedProfile,
    IReadOnlyList<AnarchyLedgerStatViewModel> LedgerStats,
    IReadOnlyList<BlackLedgerDispatchViewModel> Dispatches,
    AnarchyExplainReceiptViewModel ExplainReceipt,
    string ExportJson,
    TrustPageActionViewModel PrimaryAction,
    TrustPageActionViewModel SecondaryAction,
    PublicTrustPulsePanelViewModel? TrustPulse = null,
    SignedInTrustStatusPanelViewModel? SignedInStatus = null);

public sealed record StoryPageViewModel(
    SiteChromeViewModel Chrome,
    PublicLandingSurfaceDto Surface,
    AssetCatalogViewModel Assets,
    IReadOnlyList<ResolvedPublicCardViewModel> Workflows,
    IReadOnlyList<PublicFeatureCardDto> TrustPillars,
    IReadOnlyList<ResolvedPublicCardViewModel> Lanes,
    ReleaseExperienceViewModel ReleaseExperience,
    PublicTrustPulsePanelViewModel? TrustPulse = null,
    SignedInTrustStatusPanelViewModel? SignedInStatus = null);

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
    PublicSignalLoopSnapshotViewModel SignalLoop,
    PublicSignalProjectionPacketViewModel? SignalProjection = null,
    CampaignOsLocalProofSnapshot? CampaignOsProof = null,
    PublicTrustPulsePanelViewModel? TrustPulse = null,
    SignedInTrustStatusPanelViewModel? SignedInStatus = null);

public sealed record HorizonsPageViewModel(
    SiteChromeViewModel Chrome,
    PublicLandingSurfaceDto Surface,
    AssetCatalogViewModel Assets,
    IReadOnlyList<ResolvedPublicCardViewModel> Horizons,
    PublicTrustPulsePanelViewModel? TrustPulse = null,
    SignedInTrustStatusPanelViewModel? SignedInStatus = null);

public sealed record RoadmapPageViewModel(
    SiteChromeViewModel Chrome,
    IReadOnlyList<ResolvedPublicCardViewModel> Horizons,
    IReadOnlyList<ProgramMilestoneSummaryViewModel> Milestones,
    PublicSignalLoopSnapshotViewModel SignalLoop,
    PublicSignalProjectionPacketViewModel? SignalProjection = null,
    PublicTrustPulsePanelViewModel? TrustPulse = null);

public sealed record ShelfPageViewModel(
    SiteChromeViewModel Chrome,
    PublicLandingSurfaceDto Surface,
    AssetCatalogViewModel Assets,
    string Eyebrow,
    string Heading,
    string Intro,
    IReadOnlyList<ResolvedPublicCardViewModel> Items,
    IReadOnlyList<CreatorPublicationProjection>? PublicCreatorPublications = null,
    PublicTrustPulsePanelViewModel? TrustPulse = null,
    SignedInTrustStatusPanelViewModel? SignedInStatus = null,
    IReadOnlyList<RecapShelfEntry>? SignedInRecapShelf = null,
    IReadOnlyList<CreatorPublicationProjection>? SignedInCreatorPublications = null,
    string SignedInArtifactView = "all");

public sealed record DownloadsPageViewModel(
    SiteChromeViewModel Chrome,
    PublicLandingSurfaceDto Surface,
    AssetCatalogViewModel Assets,
    PublicReleaseManifestDto Manifest,
    ReleaseExperienceViewModel ReleaseExperience,
    FlagshipCoverageStripViewModel FlagshipCoverage,
    IReadOnlyList<ReleaseOptionViewModel>? SignedInWindowsBuilds = null,
    IReadOnlyList<WindowsProofInstallerRecord>? WindowsProofInstallers = null,
    PublicTrustPulsePanelViewModel? TrustPulse = null,
    SignedInTrustStatusPanelViewModel? SignedInStatus = null,
    PublicAccessPostureViewModel? AccessPosture = null);

public sealed record ReleaseUploadPageViewModel(
    SiteChromeViewModel Chrome,
    string Heading,
    string Summary,
    string Command,
    string HandoffCode,
    string BootstrapUrl,
    DateTimeOffset TicketExpiresAtUtc,
    string UploadUrl,
    string ReadmeUrl,
    string VerifyUrl,
    string WindowsUploadNote,
    PublicTrustPulsePanelViewModel? TrustPulse = null,
    SignedInTrustStatusPanelViewModel? SignedInStatus = null);

public sealed record KarmaForgeIntakePageViewModel(
    SiteChromeViewModel Chrome,
    string Eyebrow,
    string Heading,
    string Intro,
    string CanonicalLane,
    string EntryLane,
    KarmaForgeDashboardSummary Dashboard,
    IReadOnlyList<string> DiscoverySteps,
    IReadOnlyList<KarmaForgeExternalStageProjection> ExternalStages,
    IReadOnlyList<JourneyProofEventRef> JourneyProofEventRefs,
    KarmaForgeIntakeFormViewModel Form,
    KarmaForgeTrackDefinition SelectedTrack,
    IReadOnlyList<KarmaForgeCandidateDecisionViewModel> CandidateDecisions,
    IReadOnlyList<string> CanonicalOutputs,
    IReadOnlyList<KarmaForgeRecentSubmissionViewModel> RecentSubmissions,
    PublicTrustPulsePanelViewModel? TrustPulse = null,
    SignedInTrustStatusPanelViewModel? SignedInStatus = null);

public sealed record KarmaForgeIntakeFormViewModel(
    string ActionHref,
    bool Authenticated,
    string? SubmissionNotice,
    IReadOnlyList<string> ValidationErrors,
    IReadOnlyList<KarmaForgeOptionDefinition> TrackOptions,
    IReadOnlyList<KarmaForgeOptionDefinition> RoleOptions,
    IReadOnlyList<KarmaForgeOptionDefinition> EditionOptions,
    IReadOnlyList<KarmaForgeOptionDefinition> TableTypeOptions,
    IReadOnlyList<KarmaForgeOptionDefinition> RuleCategoryOptions,
    IReadOnlyList<KarmaForgeOptionDefinition> SeverityOptions,
    string DefaultTrackKey,
    string DefaultRespondentRole,
    string DefaultEdition,
    string DefaultTableType,
    string DefaultRuleCategory,
    string DefaultSeverity,
    string DefaultFeedbackPrompt,
    string DefaultUserWordsSummary,
    string DefaultCurrentWorkaround,
    string DefaultInterpretedNeedSummary,
    string DefaultImpactNotes,
    string DefaultShareabilityNotes,
    string DefaultReplyEmail,
    bool DefaultFollowUpAllowed,
    bool DefaultQuoteAllowed,
    bool DefaultConsentAccepted);

public sealed record KarmaForgeCandidateDecisionViewModel(
    string Key,
    string Meaning);

public sealed record KarmaForgeRecentSubmissionViewModel(
    string SubmissionId,
    string Title,
    string SubmittedLabel,
    string CandidateDecision,
    string QueueStatus);

public sealed record KarmaForgeSubmittedPageViewModel(
    SiteChromeViewModel Chrome,
    string Eyebrow,
    string Heading,
    string Intro,
    string SubmissionId,
    string TrackTitle,
    string QueueStatus,
    IReadOnlyList<TrustPageActionViewModel> Actions,
    string PacketTitle,
    string QueueSummary,
    string CandidateDecision,
    string CandidateDecisionMeaning,
    string ReporterNextAction,
    string ConsentSummary,
    IReadOnlyList<KarmaForgeExternalStageProjection> ExternalStages,
    IReadOnlyList<JourneyProofEventRef> JourneyProofEventRefs,
    IReadOnlyList<string> Highlights,
    bool FollowUpAllowed,
    IReadOnlyList<string> NextQuestions,
    IReadOnlyList<string> NextSteps,
    bool QuoteAllowed,
    string PacketJson,
    string CandidateJson,
    string ImpactHypothesisJson,
    PublicTrustPulsePanelViewModel? TrustPulse = null,
    SignedInTrustStatusPanelViewModel? SignedInStatus = null);

public sealed record StatusPageViewModel(
    SiteChromeViewModel Chrome,
    PublicReleaseManifestDto Manifest,
    ReleaseExperienceViewModel ReleaseExperience,
    CampaignOsLocalProofSnapshot? CampaignOsProof = null,
    IReadOnlyList<PublicTrustPulseRowViewModel>? LaunchHealthRows = null,
    PublicTrustPulsePanelViewModel? TrustPulse = null,
    SignedInTrustStatusPanelViewModel? SignedInStatus = null);

public sealed record DownloadDispatchPageViewModel(
    SiteChromeViewModel Chrome,
    string Eyebrow,
    string Heading,
    string Summary,
    string DispatchNote,
    string ArtifactTitle,
    string ArtifactSupportLine,
    string DownloadHref,
    string DownloadLabel,
    string? TerminalInstallCommand,
    string? BootstrapCommandLabel,
    string? BootstrapCommandIntro,
    string? BootstrapCommandNote,
    string CopyCommandLabel,
    bool CompactDispatchLayout,
    IReadOnlyList<DownloadDispatchFeatureCardViewModel> BootstrapFeatureCards,
    bool AutoStartDownload,
    bool BootstrapScriptDownload,
    bool PromoteSecondaryDownload,
    string? SecondaryDownloadHref,
    string? SecondaryDownloadLabel,
    string AccountHref,
    string AccountLabel,
    string HelpHref,
    string HelpLabel,
    string SupportHref,
    string SupportLabel,
    ReleaseDisplayViewModel Display,
    string Channel,
    string Version,
    string CurrentReleaseSummary,
    string PlatformLabel,
    string HeadLabel,
    string? ClaimExchangeUrl,
    string? ClaimCode,
    DateTimeOffset? ClaimCodeExpiresAtUtc,
    IReadOnlyList<string> Steps,
    PublicTrustPulsePanelViewModel? TrustPulse = null,
    SignedInTrustStatusPanelViewModel? SignedInStatus = null);

public sealed record DownloadDispatchFeatureCardViewModel(
    string Heading,
    string Body);

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

public sealed record PublicConciergeBranchCardViewModel(
    string BranchId,
    string Title,
    string Summary,
    string ActionHref,
    string ActionLabel,
    string Tone,
    string DestinationLabel);

public sealed record PublicConciergeWidgetViewModel(
    string StatusLabel,
    string Summary,
    string? IframeHref = null,
    string? HostLabel = null,
    string? ContentSecurityPolicy = null);

public sealed record PublicConciergePageViewModel(
    SiteChromeViewModel Chrome,
    string FlowId,
    string Eyebrow,
    string Heading,
    string Intro,
    string EntrySurfaceLabel,
    string Locale,
    bool LocaleFallbackUsed,
    IReadOnlyList<string> ProofPoints,
    IReadOnlyList<PublicConciergeBranchCardViewModel> Branches,
    IReadOnlyList<TrustPageActionViewModel> Actions,
    PublicConciergeWidgetViewModel Widget);

public sealed record CampaignInvitePrimerSectionViewModel(
    string Id,
    string Eyebrow,
    string Heading,
    string Summary,
    IReadOnlyList<string> Bullets,
    TrustPageActionViewModel PrimaryAction,
    TrustPageActionViewModel? SecondaryAction = null);

public sealed record CampaignInvitePrimerPageViewModel(
    SiteChromeViewModel Chrome,
    string InviteCode,
    bool InviteCodePresent,
    string Heading,
    string Intro,
    IReadOnlyList<string> ProofPoints,
    IReadOnlyList<CampaignInvitePrimerSectionViewModel> Sections,
    IReadOnlyList<TrustPageActionViewModel> Actions);

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

public sealed record PublicTrustPulseRowViewModel(
    string Label,
    string Value);

public sealed record PublicTrustPulseTrendPointViewModel(
    string AsOf,
    int OverallProgressPercent,
    bool Current = false);

public sealed record PublicTrustPulsePanelViewModel(
    string Eyebrow,
    string Heading,
    string Summary,
    IReadOnlyList<string> MicroProof,
    IReadOnlyList<PublicTrustPulseTrendPointViewModel> TrendSamples,
    IReadOnlyList<PublicTrustPulseRowViewModel> Rows,
    TrustPageActionViewModel PrimaryAction,
    TrustPageActionViewModel? SecondaryAction = null,
    bool MissingDesktopClientCoverage = false,
    bool ParityClaimsReviewRequired = false,
    string? RouteGuardSummary = null);

public sealed record PrivacyBoundaryDomainViewModel(
    string Label,
    string Owner,
    string RetentionSummary,
    string RedactionSummary,
    string PublicProjection,
    string SignedInProjection);

public sealed record PrivacyBoundarySurfaceRuleViewModel(
    string Label,
    string Summary,
    string BlockedSummary);

public sealed record PrivacyBoundaryPanelViewModel(
    string Eyebrow,
    string Heading,
    string Summary,
    IReadOnlyList<string> MicroProof,
    IReadOnlyList<PrivacyBoundaryDomainViewModel> Domains,
    IReadOnlyList<PrivacyBoundarySurfaceRuleViewModel> SurfaceRules,
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
    string InstallAccessHref,
    string InstallAccessLabel,
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
    string? ContextHint = null,
    string? InstallRailHref = null,
    string? InstallRailLabel = null,
    string? InstallRailSummary = null,
    bool RecoveryModeOnly = false);

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
    SupportCasePresentationViewModel? TrackedCaseSummary = null,
    PublicTrustPulsePanelViewModel? TrustPulse = null,
    SignedInTrustStatusPanelViewModel? SignedInStatus = null);

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
    PublicTrustPulsePanelViewModel? TrustPulse = null,
    SignedInTrustStatusPanelViewModel? SignedInStatus = null,
    PrivacyBoundaryPanelViewModel? PrivacyBoundary = null);

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
    IReadOnlyList<TrustPageActionViewModel> Actions,
    PublicTrustPulsePanelViewModel? TrustPulse = null,
    SignedInTrustStatusPanelViewModel? SignedInStatus = null,
    PublicAccessPostureViewModel? AccessPosture = null);

public sealed record ParticipatePageViewModel(
    SiteChromeViewModel Chrome,
    PublicLandingSurfaceDto Surface,
    AssetCatalogViewModel Assets,
    IReadOnlyList<ResolvedPublicCardViewModel> PublicLane,
    IReadOnlyList<ResolvedPublicCardViewModel> SignedInLane,
    PublicSignalLoopSnapshotViewModel SignalLoop,
    PublicSignalProjectionPacketViewModel? SignalProjection = null,
    PublicSignalOperationsPacketViewModel? SignalOperations = null,
    PublicTrustPulsePanelViewModel? TrustPulse = null,
    SignedInTrustStatusPanelViewModel? SignedInStatus = null);

public sealed record PublicSignalLoopSnapshotViewModel(
    int OpenMilestoneCount,
    int ClaimedMilestoneCount,
    int HighDifficultyMilestoneCount,
    int RoadmapFollowUpCount,
    int ShippedFollowUpCount,
    IReadOnlyList<ProgramMilestoneSummaryViewModel> MilestoneFollowUp,
    IReadOnlyList<ResolvedPublicCardViewModel> RoadmapFollowUp,
    IReadOnlyList<ResolvedPublicCardViewModel> ShippedFollowUp,
    string FollowSettingsHref,
    string FollowSettingsLabel);

public sealed record PublicSignalProjectionPacketViewModel(
    string Eyebrow,
    string Heading,
    string Summary,
    string Vendor,
    string Role,
    string TruthPosture,
    string PublicPath,
    string FallbackPath,
    string PolicyStatus,
    string CoreRule,
    IReadOnlyList<string> AuthorityFlow,
    IReadOnlyList<string> DecisionRoutes,
    IReadOnlyList<string> CanonicalSources,
    IReadOnlyList<string> Forbidden,
    IReadOnlyList<string> CloseoutRequirements,
    string PublicWarning,
    IReadOnlyList<string> BoardTargets,
    IReadOnlyList<JourneyProofEventRef> JourneyProofEventRefs,
    string PolicySource,
    string PipelineSource,
    string RegistrySource);

public sealed record PublicSignalHostedRouteViewModel(
    string Label,
    string PublicPath,
    string? HostedHref,
    string StatusLabel,
    string Summary);

public sealed record PublicSignalDeliveryOutcomeIngressViewModel(
    string Label,
    string ProviderKey,
    string StatusLabel,
    string Summary,
    string SecretHeader,
    IReadOnlyList<string> Routes);

public sealed record PublicSignalCategoryRoutingViewModel(
    string Label,
    string OwnerRepo,
    string FollowUpLane,
    string Summary,
    bool SupportMisrouteLikely,
    bool PrivacySensitive);

public sealed record PublicSignalWebhookReceiptViewModel(
    string ReceiptId,
    string ProviderEventId,
    string EventType,
    string ActionLabel,
    string StatusLabel,
    string BoardLabel,
    string CategoryLabel,
    string ItemReference,
    bool CloseoutCandidate,
    bool VoterNotificationAllowed,
    string HotFilterKey,
    string HotFilterLabel,
    int HotFilterCount,
    string HotFilterSummary,
    string PayloadSha256,
    DateTimeOffset ReceivedAtUtc,
    DateTimeOffset? ProviderOccurredAtUtc);

public sealed record PublicSignalRoutingReceiptViewModel(
    string ReceiptId,
    string SourceReceiptId,
    string RouteKind,
    string StatusLabel,
    string TargetPath,
    string Summary,
    string SourceHotFilterKey,
    string SourceHotFilterLabel,
    int SourceHotFilterCount,
    string SourceHotFilterSummary,
    DateTimeOffset RecordedAtUtc);

public sealed record PublicSignalCloseoutDeliveryReceiptViewModel(
    string ReceiptId,
    string SourceReceiptId,
    string StatusLabel,
    string DeliveryState,
    string DeliveryLane,
    string TemplateId,
    string RecipientScopeRef,
    int RecipientScopeCount,
    string ConsentSourceRef,
    string DeliveryReason,
    string Summary,
    bool VoterNotificationAllowed,
    bool PublicClaimAllowed,
    string SourceHotFilterKey,
    string SourceHotFilterLabel,
    int SourceHotFilterCount,
    string SourceHotFilterSummary,
    DateTimeOffset RecordedAtUtc);

public sealed record PublicSignalCloseoutQueueReceiptViewModel(
    string ReceiptId,
    string SourceReceiptId,
    string StatusLabel,
    string QueueState,
    string QueueLane,
    string DispatchTool,
    string DispatchAction,
    string JourneyEventKey,
    string? GovernorDecisionRef,
    string ReleaseProofRoute,
    string? ReleaseProofReceiptId,
    string QueueReason,
    string Summary,
    bool ReadyForOutbox,
    bool PublicClaimAllowed,
    string SourceHotFilterKey,
    string SourceHotFilterLabel,
    int SourceHotFilterCount,
    string SourceHotFilterSummary,
    DateTimeOffset RecordedAtUtc);

public sealed record PublicSignalCloseoutDispatchReceiptViewModel(
    string ReceiptId,
    string SourceReceiptId,
    string StatusLabel,
    string DeliveryState,
    string DeliveryId,
    string? ProviderMessageId,
    string TemplateId,
    string TemplateVersion,
    string RecipientRef,
    string AddressHash,
    string ConsentSourceRef,
    string SuppressionCheck,
    string GovernorDecisionRef,
    string ReleaseProofReceiptId,
    string IdempotencyKey,
    string Summary,
    string? Error,
    bool PublicClaimAllowed,
    int RecoveryAttemptCount,
    string? LastRecoveryStatus,
    string? LastProviderState,
    DateTimeOffset? NextAutomaticRetryAtUtc,
    DateTimeOffset? LastOutcomeAtUtc,
    DateTimeOffset RequestedAtUtc,
    DateTimeOffset? AcceptedAtUtc,
    DateTimeOffset? LastRecoveryAtUtc);

public sealed record PublicSignalJourneyReceiptViewModel(
    string ReceiptId,
    string SourceReceiptId,
    string EventKey,
    string StatusLabel,
    string GovernorDecisionRef,
    string ReleaseProofReceiptId,
    int RecipientCount,
    int SentCount,
    string Summary,
    bool PublicClaimAllowed,
    string SourceHotFilterKey,
    string SourceHotFilterLabel,
    int SourceHotFilterCount,
    string SourceHotFilterSummary,
    DateTimeOffset RecordedAtUtc);

public sealed record PublicSignalDeliveryOutcomeReceiptViewModel(
    string ReceiptId,
    string OutcomeEventId,
    string Provider,
    string DispatchReceiptId,
    string SourceReceiptId,
    string DeliveryId,
    string? ProviderMessageId,
    string RecipientRef,
    string AddressHash,
    string IdentityMatchMode,
    string ProviderState,
    string StatusLabel,
    string SuppressionCheck,
    DateTimeOffset? RetryAtUtc,
    string Summary,
    string? Reason,
    bool PublicClaimAllowed,
    DateTimeOffset OccurredAtUtc,
    DateTimeOffset RecordedAtUtc);

public sealed record PublicSignalRecipientThreadViewModel(
    string RecipientRef,
    string AddressHash,
    string SourceReceiptId,
    string SourceLabel,
    string CurrentStageLabel,
    string Summary,
    string QueueReceiptId,
    string QueueState,
    string QueueStatusLabel,
    DateTimeOffset QueueRecordedAtUtc,
    string DispatchReceiptId,
    string DispatchState,
    string DispatchStatusLabel,
    DateTimeOffset DispatchRequestedAtUtc,
    string? OutcomeReceiptId,
    string? OutcomeStatusLabel,
    string? OutcomeProvider,
    string? OutcomeProviderState,
    string? OutcomeIdentityMatchMode,
    DateTimeOffset? OutcomeRecordedAtUtc,
    string? JourneyReceiptId,
    string? JourneyStatusLabel,
    string? JourneyEventKey,
    DateTimeOffset? JourneyRecordedAtUtc,
    DateTimeOffset LastTouchedAtUtc,
    bool PublicClaimAllowed);

public sealed record PublicSignalReconcileRunReceiptViewModel(
    string RunReceiptId,
    string Status,
    int CandidateReceiptCount,
    int ReadyCandidateCount,
    int ReplayCandidateCount,
    int DispatchReceiptsCreated,
    int JourneyReceiptsRecorded,
    string Summary,
    DateTimeOffset RecordedAtUtc);

public sealed record PublicSignalOperationsPacketViewModel(
    string Eyebrow,
    string Heading,
    string Summary,
    string HostedDomainLabel,
    string HostedProjectionSummary,
    bool HostedProjectionReady,
    string WebhookStatusLabel,
    string WebhookSummary,
    string VoterCloseoutStatusLabel,
    string VoterCloseoutSummary,
    string RecipientProjectionOwner,
    string FollowSettingsPath,
    string RecipientProjectionStatusLabel,
    string RecipientProjectionSummary,
    string ProjectionSourceRef,
    int ProjectedRecipientCount,
    string ConsentStatusLabel,
    string ConsentSummary,
    string ConsentSourceRef,
    string QueueStatusLabel,
    string QueueSummary,
    string GovernorStatusLabel,
    string GovernorSummary,
    string? GovernorDecisionRef,
    string ReleaseProofStatusLabel,
    string ReleaseProofSummary,
    string ReleaseProofRoute,
    string? ReleaseProofReceiptId,
    int ReceiptCount,
    int CloseoutReceiptCount,
    DateTimeOffset? LastReceiptAtUtc,
    int RoutingReceiptCount,
    int ModerationReceiptCount,
    int CloseoutDeliveryReceiptCount,
    int CloseoutDeliveryCandidateCount,
    int CloseoutQueueReceiptCount,
    int CloseoutQueueReadyCount,
    int CloseoutDispatchReceiptCount,
    int CloseoutDispatchSentCount,
    int JourneyReceiptCount,
    int DeliveryOutcomeReceiptCount,
    int AutomaticRetryPendingCount,
    DateTimeOffset? LastDeliveryOutcomeAtUtc,
    int ReplayCandidateCount,
    int ReconcileRunCount,
    DateTimeOffset? LastReconcileAtUtc,
    int DeliveryRecoveryCandidateCount,
    int SuppressedDispatchCount,
    int DeliveryRecoveryRunCount,
    DateTimeOffset? LastDeliveryRecoveryAtUtc,
    int RetryExpiryCandidateCount,
    int RetryExpiryRunCount,
    DateTimeOffset? LastRetryExpiryAtUtc,
    int CategoryCount,
    int MisrouteLikelyCount,
    int PrivacySensitiveCount,
    IReadOnlyList<PublicSignalHostedRouteViewModel> HostedRoutes,
    IReadOnlyList<PublicSignalDeliveryOutcomeIngressViewModel> DeliveryOutcomeIngresses,
    IReadOnlyList<PublicSignalCategoryRoutingViewModel> Categories,
    IReadOnlyList<PublicSignalWebhookReceiptViewModel> RecentReceipts,
    IReadOnlyList<PublicSignalRoutingReceiptViewModel> RecentRoutingReceipts,
    IReadOnlyList<PublicSignalCloseoutDeliveryReceiptViewModel> RecentCloseoutReceipts,
    IReadOnlyList<PublicSignalCloseoutQueueReceiptViewModel> RecentQueueReceipts,
    IReadOnlyList<PublicSignalCloseoutDispatchReceiptViewModel> RecentDispatchReceipts,
    IReadOnlyList<PublicSignalJourneyReceiptViewModel> RecentJourneyReceipts,
    IReadOnlyList<PublicSignalDeliveryOutcomeReceiptViewModel> RecentDeliveryOutcomes,
    IReadOnlyList<PublicSignalRecipientThreadViewModel> RecentRecipientThreads,
    IReadOnlyList<PublicSignalReconcileRunReceiptViewModel> RecentReconcileRuns,
    IReadOnlyList<PublicSignalReconcileRunReceiptViewModel> RecentRecoveryRuns,
    IReadOnlyList<PublicSignalReconcileRunReceiptViewModel> RecentRetryExpiryRuns,
    IReadOnlyList<string> Rules);

public sealed record PublicSignalOperationsDetailViewModel(
    string DetailKindLabel,
    string DetailKeyLabel,
    string DetailKey,
    string Eyebrow,
    string Heading,
    string Summary,
    string FilterKey,
    string FilterLabel,
    bool FilterApplied,
    string BackHref,
    string BackLabel,
    string AggregateArtifactHref,
    string DetailArtifactHref,
    string? RelatedHref,
    string? RelatedLabel,
    IReadOnlyList<PublicSignalOperationsDetailPivotViewModel> SavedPivots,
    PublicSignalWebhookReceiptViewModel? SourceReceipt,
    IReadOnlyList<PublicSignalRoutingReceiptViewModel> RoutingReceipts,
    IReadOnlyList<PublicSignalCloseoutDeliveryReceiptViewModel> CloseoutReceipts,
    IReadOnlyList<PublicSignalCloseoutQueueReceiptViewModel> QueueReceipts,
    IReadOnlyList<PublicSignalRecipientThreadViewModel> RecipientThreads,
    IReadOnlyList<PublicSignalCloseoutDispatchReceiptViewModel> DispatchReceipts,
    IReadOnlyList<PublicSignalDeliveryOutcomeReceiptViewModel> DeliveryOutcomes,
    IReadOnlyList<PublicSignalJourneyReceiptViewModel> JourneyReceipts);

public sealed record PublicSignalOperationsDetailPivotViewModel(
    string Key,
    string Label,
    string Summary,
    int Count,
    string Href,
    string ArtifactHref,
    bool Current);

public sealed record PublicSignalOperationsDetailPageViewModel(
    SiteChromeViewModel Chrome,
    PublicSignalOperationsDetailViewModel Detail);

public sealed record PublicSignalOperationsLookupResultViewModel(
    string ResultKindLabel,
    string MatchReason,
    string KeyLabel,
    string Key,
    string Heading,
    string Summary,
    string FilterKey,
    string FilterLabel,
    string Href,
    string ArtifactHref,
    DateTimeOffset LastTouchedAtUtc);

public sealed record PublicSignalOperationsLookupViewModel(
    string Query,
    string Scope,
    string ScopeLabel,
    bool QueryProvided,
    string Eyebrow,
    string Heading,
    string Summary,
    int ResultCount,
    IReadOnlyList<PublicSignalOperationsLookupResultViewModel> Results);

public sealed record PublicSignalOperationsLookupPageViewModel(
    SiteChromeViewModel Chrome,
    PublicSignalOperationsLookupViewModel Lookup);

public sealed record PackageClassCardViewModel(
    string Label,
    string Summary,
    IReadOnlyList<string> Rules);

public sealed record PackageCatalogEntryViewModel(
    string PackageId,
    string Title,
    string Summary,
    string ClassLabel,
    string StatusLabel,
    string CompatibilitySummary,
    string GovernanceSummary,
    string EvidenceSummary,
    int VoteCount,
    int FollowCount,
    string DetailHref);

public sealed record PackageReceiptCardViewModel(
    string ReceiptId,
    string PackageId,
    string PackageTitle,
    string ActionLabel,
    string ActorLabel,
    string RouteSummary,
    string RecordedAtLabel,
    string Href);

public sealed record PackageCatalogPageViewModel(
    SiteChromeViewModel Chrome,
    string Eyebrow,
    string Heading,
    string Intro,
    bool SignedInScope,
    string ScopeLabel,
    IReadOnlyList<PackageClassCardViewModel> Classes,
    IReadOnlyList<PackageCatalogEntryViewModel> Packages,
    IReadOnlyList<PackageReceiptCardViewModel> Receipts,
    TrustPageActionViewModel PrimaryAction,
    TrustPageActionViewModel? SecondaryAction,
    PublicTrustPulsePanelViewModel? TrustPulse = null,
    SignedInTrustStatusPanelViewModel? SignedInStatus = null);

public sealed record PackageDetailPageViewModel(
    SiteChromeViewModel Chrome,
    string ScopeLabel,
    PackageCatalogEntryViewModel Package,
    IReadOnlyList<string> CompatibilityNotes,
    IReadOnlyList<string> GovernanceNotes,
    IReadOnlyList<PackageReceiptCardViewModel> RecentReceipts,
    PackageReceiptCardViewModel? LatestVoteReceipt,
    PackageReceiptCardViewModel? LatestFollowReceipt,
    bool CanInteract,
    bool CanRevokeVote,
    bool CanRevokeFollow,
    string VoteActionHref,
    string FollowActionHref,
    string? RevokeVoteActionHref,
    string? RevokeFollowActionHref,
    string VoteActionLabel,
    string FollowActionLabel,
    TrustPageActionViewModel PrimaryAction,
    TrustPageActionViewModel? SecondaryAction,
    PublicTrustPulsePanelViewModel? TrustPulse = null,
    SignedInTrustStatusPanelViewModel? SignedInStatus = null);

public sealed record PackageActionReceiptPageViewModel(
    SiteChromeViewModel Chrome,
    string Eyebrow,
    string Heading,
    string Intro,
    PackageCatalogEntryViewModel Package,
    PackageReceiptCardViewModel Receipt,
    TrustPageActionViewModel PrimaryAction,
    TrustPageActionViewModel? SecondaryAction,
    PublicTrustPulsePanelViewModel? TrustPulse = null,
    SignedInTrustStatusPanelViewModel? SignedInStatus = null);

public sealed record MobileRoleCardViewModel(
    string Label,
    string Summary,
    string Href,
    bool Current);

public sealed record MobileCapabilityCardViewModel(
    string Label,
    string Summary);

public sealed record MobileProjectionPageViewModel(
    SiteChromeViewModel Chrome,
    string Eyebrow,
    string Heading,
    string Intro,
    string CurrentRoleLabel,
    string InstallabilitySummary,
    IReadOnlyList<MobileRoleCardViewModel> Roles,
    IReadOnlyList<MobileCapabilityCardViewModel> Capabilities,
    TrustPageActionViewModel PrimaryAction,
    TrustPageActionViewModel SecondaryAction,
    PublicTrustPulsePanelViewModel? TrustPulse = null,
    SignedInTrustStatusPanelViewModel? SignedInStatus = null);

public sealed record ReadyVerdictCardViewModel(
    string RoleId,
    string RoleLabel,
    string Status,
    string StatusLabel,
    string Summary,
    IReadOnlyList<string> BlockingReasons,
    IReadOnlyList<string> ChangedSinceLastSession,
    IReadOnlyList<TrustPageActionViewModel> Actions,
    string NextBestScreen,
    IReadOnlyList<string> ProofReceipts);

public sealed record ReadyRoleKitViewModel(
    string KitId,
    string RoleLane,
    string Label,
    string Summary,
    string DownloadHref,
    IReadOnlyList<string> Highlights);

public sealed record ReadyPacketAssetViewModel(
    string RoleId,
    string Label,
    string Summary,
    string MarkdownHref,
    string JsonHref);

public sealed record ReadyForTonightPageViewModel(
    SiteChromeViewModel Chrome,
    string Eyebrow,
    string Heading,
    string Intro,
    string VerdictSummary,
    IReadOnlyList<string> SummaryPoints,
    IReadOnlyList<ReadyVerdictCardViewModel> Verdicts,
    IReadOnlyList<ReadyRoleKitViewModel> RoleKits,
    IReadOnlyList<ReadyPacketAssetViewModel> Packets,
    TrustPageActionViewModel PrimaryAction,
    TrustPageActionViewModel SecondaryAction,
    TrustPageActionViewModel TertiaryAction,
    PublicTrustPulsePanelViewModel? TrustPulse = null,
    SignedInTrustStatusPanelViewModel? SignedInStatus = null);

public sealed record KnowledgeFabricReceiptViewModel(
    string ReceiptId,
    string Topic,
    string Summary,
    string Provenance,
    string Route,
    string Status);

public sealed record KnowledgeFabricPageViewModel(
    SiteChromeViewModel Chrome,
    string Eyebrow,
    string Heading,
    string Intro,
    IReadOnlyList<string> SummaryPoints,
    IReadOnlyList<KnowledgeFabricReceiptViewModel> Receipts,
    TrustPageActionViewModel PrimaryAction,
    TrustPageActionViewModel SecondaryAction,
    TrustPageActionViewModel TertiaryAction,
    PublicTrustPulsePanelViewModel? TrustPulse = null,
    SignedInTrustStatusPanelViewModel? SignedInStatus = null);

public sealed record NexusPanReceiptViewModel(
    string ReceiptId,
    string Topic,
    string Summary,
    string Route,
    string Status);

public sealed record NexusPanContinuityPageViewModel(
    SiteChromeViewModel Chrome,
    string Eyebrow,
    string Heading,
    string Intro,
    string VerdictSummary,
    string PlatformSummary,
    IReadOnlyList<string> SummaryPoints,
    int ActiveInstallationCount,
    int ActiveGrantCount,
    int PendingClaimCount,
    int PendingBrowserCallbackCount,
    IReadOnlyList<string> PlatformLabels,
    IReadOnlyList<NexusPanReceiptViewModel> Receipts,
    TrustPageActionViewModel PrimaryAction,
    TrustPageActionViewModel SecondaryAction,
    TrustPageActionViewModel TertiaryAction,
    PublicTrustPulsePanelViewModel? TrustPulse = null,
    SignedInTrustStatusPanelViewModel? SignedInStatus = null);

public sealed record MediaArtifactCardViewModel(
    string Id,
    string Label,
    string Summary,
    string MarkdownRoute,
    string JsonRoute,
    IReadOnlyList<string> Highlights);

public sealed record MediaArtifactHorizonPageViewModel(
    SiteChromeViewModel Chrome,
    string Eyebrow,
    string Heading,
    string Intro,
    string BoundaryLine,
    IReadOnlyList<string> SummaryPoints,
    IReadOnlyList<MediaArtifactCardViewModel> Documents,
    TrustPageActionViewModel PrimaryAction,
    TrustPageActionViewModel SecondaryAction,
    TrustPageActionViewModel TertiaryAction,
    PublicTrustPulsePanelViewModel? TrustPulse = null,
    SignedInTrustStatusPanelViewModel? SignedInStatus = null);

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
    IReadOnlyList<string> MicroProof,
    PublicTrustPulsePanelViewModel? TrustPulse = null,
    SignedInTrustStatusPanelViewModel? SignedInStatus = null);

public sealed record PublicCreatorPublicationPageViewModel(
    SiteChromeViewModel Chrome,
    CreatorPublicationProjection Publication,
    string BackHref,
    string RouteState,
    PublicRouteReceiptViewModel? RouteReceipt,
    string? BoundedFailureReason,
    IReadOnlyList<string> RequiredReceiptRefs,
    PublicTrustPulsePanelViewModel? TrustPulse = null,
    SignedInTrustStatusPanelViewModel? SignedInStatus = null);

public sealed record PublicRouteReceiptViewModel(
    string ReceiptId,
    string PackageId,
    string MatchedRoute,
    string MatchMode,
    string Summary);

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
    ReleaseExperienceViewModel ReleaseExperience,
    HubUserDto User,
    AccountLinkSummaryDto Links,
    HubUserExperienceDto Experience,
    InstallLinkingSummaryDto InstallLinking,
    IReadOnlyList<SupportCaseProjection> SupportCases,
    IReadOnlyList<SupportCasePresentationViewModel> SupportCaseSummaries,
    AccountCampaignSummary CampaignSpine,
    CampaignWorkspaceServerPlaneProjection? LeadWorkspaceServerPlane,
    HomePrimaryActionViewModel PrimaryAction,
    FlagshipCoverageStripViewModel FlagshipCoverage,
    SignedInTrustStatusPanelViewModel? SignedInStatus,
    IReadOnlyList<ResolvedPublicCardViewModel> NowRail,
    IReadOnlyList<ResolvedPublicCardViewModel> HorizonRail);

public sealed record ProgramMilestoneSummaryViewModel(
    string Id,
    string Title,
    string WaveLabel,
    string StatusKey,
    string StatusLabel,
    string CasualSummary,
    string DifficultyLabel,
    string DifficultySummary,
    bool Claimed,
    string ClaimedLabel,
    string ClaimedSummary,
    string DependencySummary,
    IReadOnlyList<ProgramMilestoneDependencyViewModel> Dependencies);

public sealed record ProgramMilestoneDependencyViewModel(
    string Id,
    string Title,
    string StatusLabel);

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
    EntitlementSyncReceiptProjection? EntitlementSyncReceipts = null,
    CampaignWorkspaceProjection? SelectedWorkspace = null,
    CampaignWorkspaceServerPlaneProjection? SelectedWorkspaceServerPlane = null,
    RosterTransferPlannerProjection? SelectedWorkspaceRosterTransferPlan = null,
    CampaignPrepLibrarySearchResponse? SelectedWorkspacePrepLibrarySearch = null,
    string? SelectedWorkspacePrepLibraryQuery = null,
    RunProjection? SelectedRun = null,
    BuildLabHandoffProjection? SelectedBuildLabHandoff = null,
    RulesNavigatorAnswerProjection? SelectedRulesNavigatorAnswer = null,
    CreatorPublicationProjection? SelectedCreatorPublication = null,
    HubDraftDetailProjection? SelectedCreatorPublicationDraftDetail = null,
    HubPublicationReceipt? SelectedCreatorPublicationReceipt = null,
    SignedInTrustStatusPanelViewModel? SignedInTrustStatus = null,
    PrivacyBoundaryPanelViewModel? PrivacyBoundary = null,
    UserRecognitionSummaryDto? ParticipationRecognition = null,
    SponsorSessionStatusDto? ParticipationSession = null,
    IReadOnlyList<ContributionReceiptDto>? ParticipationReceipts = null,
    IReadOnlyList<PublicPackageReceipt>? ParticipationPackageReceipts = null,
    IReadOnlyList<KarmaForgeSubmissionProjection>? ParticipationKarmaSubmissions = null,
    IReadOnlyList<ParticipationOperatorNotificationReceipt>? ParticipationActivityReceipts = null);

public sealed record AuthPageViewModel(
    SiteChromeViewModel Chrome,
    string Heading,
    string SupportLine,
    string NextPath,
    bool CreateAccount,
    bool GoogleAvailable,
    string? GoogleUnavailableReason,
    string GoogleStartHref,
    PublicAccessPostureViewModel? AccessPosture = null);

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
