using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.Services.InstallLinking;
using Chummer.Run.Api.Services.KarmaForge;
using Chummer.Run.Api.Services.Support;
using Chummer.Run.Registry.Services;

namespace Chummer.Run.Api;

internal static class ServiceCollectionBoundedContextExtensions
{
    public static IServiceCollection AddHubPublicGuideContext(this IServiceCollection services)
    {
        services.AddHttpContextAccessor();
        services.AddSingleton<PublicCanonFileLoader>();
        services.AddSingleton<PublicRouteCatalogService>();
        services.AddSingleton<PublicActionResolver>();
        services.AddSingleton<PublicLandingService>();
        services.AddSingleton<FlipLinkDocumentPortalService>();
        services.AddSingleton<PublicPackageCatalogService>();
        services.AddSingleton<PublicFlagshipCoverageService>();
        services.AddSingleton<PublicTrustContentService>();
        services.AddSingleton<PublicPrivacyBoundaryService>();
        services.AddSingleton<PublicSignalProjectionService>();
        services.AddSingleton<PublicSignalOperationsService>();
        services.AddSingleton<PublicConciergeStore>();
        services.AddSingleton<PublicConciergeService>();
        services.AddHostedService<PublicSignalRetryExpiryWorker>();
        services.AddSingleton<PublicNavigationService>();
        services.AddSingleton<HubPageChromeService>();
        services.AddSingleton<ReadyForTonightService>();
        services.AddSingleton<KnowledgeFabricService>();
        services.AddSingleton<NexusPanContinuityService>();
        services.AddSingleton<MediaArtifactHorizonsService>();
        services.AddSingleton<CommunityCreatorHorizonsService>();
        services.AddSingleton<WaveEightHorizonsService>();
        services.AddSingleton<KarmaForgeStore>();
        services.AddSingleton<KarmaForgeDiscoveryService>();
        services.AddSingleton<BuildGhostConciergeService>();
        services.AddSingleton<BlackLedgerPublicStatsService>();
        services.AddSingleton<BlackLedgerDispatchService>();
        services.AddSingleton<BlackLedgerFactionOnboardingService>();
        services.AddSingleton<BlackLedgerWorldTickBriefingService>();
        services.AddSingleton<BeHumanEventAdapterPostureService>();
        services.AddSingleton<AnarchyPreviewService>();
        services.AddSingleton<TeableKarmaForgeReviewBoardService>();
        services.AddHostedService<TeableKarmaForgeReviewBoardSyncWorker>();
        services.AddSingleton<WeeklyProductPulseArtifactService>();
        services.AddSingleton<PublicProgressService>();
        services.AddSingleton<PublicTrustPulseService>();
        services.AddSingleton<CampaignOsLocalProofService>();
        services.AddSingleton<PublicReleaseManifestService>();
        services.AddSingleton<WindowsProofInstallerService>();
        services.AddSingleton<AurPackageCatalogService>();
        services.AddSingleton<ReleaseSelectionService>();
        services.AddSingleton<SignedInTrustStatusService>();
        return services;
    }

    public static IServiceCollection AddHubAccountsAndCommunityContext(this IServiceCollection services)
    {
        services.AddSingleton<CommunityStore>();
        services.AddSingleton<TeableUserProjectionService>();
        services.AddSingleton<TeableBlackLedgerWorldTickService>();
        services.AddSingleton<TeableHeyyScamChatService>();
        services.AddSingleton<TeableExecutiveAssistantChannelService>();
        services.AddHostedService<TeableUserProjectionSyncWorker>();
        services.AddHostedService<TeableBlackLedgerWorldTickSyncWorker>();
        services.AddHostedService<TeableHeyyScamChatSyncWorker>();
        services.AddHostedService<TeableExecutiveAssistantChannelSyncWorker>();
        services.AddHttpClient();
        services.AddSingleton<AccountService>();
        services.AddSingleton<IdentityLinkService>();
        services.AddSingleton<UserExperienceService>();
        services.AddSingleton<GroupService>();
        services.AddSingleton<ReusableAccountFlowService>();
        services.AddSingleton<RewardService>();
        services.AddSingleton<EntitlementService>();
        services.AddSingleton<BrilliantDirectoriesBillingStore>();
        services.AddSingleton<BrilliantDirectoriesBillingService>();
        services.AddSingleton<PayFunnelsBillingStore>();
        services.AddSingleton<PayFunnelsBillingService>();
        services.AddSingleton<LeaderboardService>();
        services.AddSingleton<LedgerService>();
        services.AddHttpClient<ParticipationOperatorNotificationService>();
        services.AddHttpClient<ExecutiveAssistantChannelMessagingService>();
        services.AddHttpClient<HeyyScamChatService>();
        services.AddHostedService<HeyyScamChatDigestWorker>();
        services.AddSingleton<BlackLedgerNewsRecipientResolver>();
        services.AddHttpClient<BlackLedgerTickNewsNotificationService>();
        services.AddHttpClient<BlackLedgerAdvisoryService>();
        services.AddHostedService<BlackLedgerTickNewsDispatchWorker>();
        services.AddScoped<BoostSessionService>();
        return services;
    }

    public static IServiceCollection AddHubCampaignSpineContext(this IServiceCollection services)
    {
        services.AddSingleton<WorkspaceLifecyclePolicyService>();
        services.AddSingleton<RunsiteOrientationRequestComposerService>();
        services.AddSingleton<IHubPublicationDraftService, HubPublicationDraftService>();
        services.AddSingleton<CampaignArtifactRegistryBridge>();
        services.AddSingleton<CreatorPublicationRegistryBridge>();
        services.AddSingleton<PublicCreatorPublicationDiscoveryService>();
        services.AddSingleton<CampaignSpineService>();
        services.AddSingleton<GmSessionVenueStore>();
        services.AddSingleton<IGmSessionVenueAdapter, BeHumanGmSessionVenueAdapter>();
        services.AddSingleton<GmSessionVenueService>();
        services.AddSingleton<GmSessionVideoFoundryStore>();
        services.AddSingleton<GmSessionVideoFoundryService>();
        services.AddSingleton<PromptFoundryStore>();
        services.AddSingleton<PromptFoundryService>();
        services.AddSingleton<CampaignFederationOrchestrationService>();
        services.AddSingleton<CampaignWorkspaceServerPlaneService>();
        services.AddSingleton<CampaignFederationOrchestrationService>();
        return services;
    }

    public static IServiceCollection AddHubControlAndSupportContext(this IServiceCollection services)
    {
        services.AddSingleton<SupportStore>();
        services.AddSingleton<SupportAttachmentStorageService>();
        services.AddSingleton<SupportCaseService>();
        services.AddSingleton<SupportCasePresentationService>();
        services.AddSingleton<SupportConciergePacketService>();
        services.AddSingleton<HostedCompanionPacketService>();
        services.AddSingleton<HostedProofContractService>();
        services.AddSingleton<HostedBoundedContextCoverageService>();
        services.AddSingleton<RegistryTruthBindingService>();
        services.AddSingleton<PrivacyBoundedSupportStatusService>();
        services.AddSingleton<PublicSignalToCanonPacketService>();
        services.AddSingleton<ExecutiveAssistantCredentialCatalogService>();
        services.AddSingleton<SupportAssistantService>();
        services.AddSingleton<IFirstPartySupportAssistant>(static provider => provider.GetRequiredService<SupportAssistantService>());
        services.AddSingleton<AnswerlyRuntimePolicy>();
        services.AddSingleton<RuleSafeOutputGate>();
        services.AddSingleton<RulesCoachRouter>();
        services.AddSingleton<AnswerlyHumanizerAdapter>();
        services.AddSingleton<RuleGhostService>();
        services.AddSingleton<AnswerlyOpenAiCompatService>();
        services.AddSingleton<IChummerAssistantAdapter, AnswerlySupportAssistantAdapter>();
        services.AddSingleton<CrashSupportService>();
        services.AddHttpClient<SupportProgressEmailWorkflowService>();
        return services;
    }

    public static IServiceCollection AddHubInstallAndOrchestrationAdapters(this IServiceCollection services)
    {
        services.AddSingleton<InstallLinkingStore>();
        services.AddSingleton<InstallLinkingService>();
        services.AddSingleton<InstallLinkedWorkspaceSnapshotStore>();
        services.AddSingleton<InstallLinkedWorkspaceSnapshotService>();
        services.AddSingleton<AccountDesktopLaunchTicketService>();
        services.AddSingleton<PersonalizedInstallScriptService>();
        services.AddSingleton<InstallBootstrapTicketService>();
        services.AddSingleton<ReleaseBundlePromotionService>();
        services.AddSingleton<ReleaseBundleUploadSessionService>();
        services.AddSingleton<ReleaseUploadTicketService>();
        services.AddSingleton<ArtifactFactoryOrchestrationService>();
        services.AddSingleton<FleetReceiptVerifier>();
        services.AddSingleton<HubEmailLinkVerificationService>();
        services.AddSingleton<HubIdentitySubjectCache>();
        services.AddHttpClient<FleetBridgeService>();
        services.AddHttpClient<HubIdentityClient>();
        services.AddHttpClient<HubBrowserAuthService>();
        services.AddHttpClient<HubGoogleAuthService>();
        return services;
    }
}
